#!/usr/bin/env python3
"""
Auto-scaling management script for Autodesk Agents Unified
Provides horizontal scaling based on metrics and load
"""

import os
import time
import json
import logging
import argparse
import requests
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ScalingConfig:
    """Configuration for auto-scaling"""
    min_replicas: int
    max_replicas: int
    target_cpu_percent: float
    target_memory_percent: float
    target_response_time_ms: float
    scale_up_threshold: float
    scale_down_threshold: float
    cooldown_period: int
    metrics_window: int


@dataclass
class ScalingMetrics:
    """Current system metrics for scaling decisions"""
    cpu_percent: float
    memory_percent: float
    response_time_ms: float
    request_rate: float
    error_rate: float
    current_replicas: int
    timestamp: datetime


class AutoScaler:
    """Manages automatic horizontal scaling of the agent system"""
    
    def __init__(self, config: ScalingConfig, environment: str):
        self.config = config
        self.environment = environment
        self.last_scale_time = datetime.min
        self.metrics_history: List[ScalingMetrics] = []
        
        # Prometheus configuration
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self.compose_file = "docker-compose.prod.yml" if environment == "production" else "docker-compose.yml"
    
    def run_command(self, command: List[str]) -> subprocess.CompletedProcess:
        """Run a command with logging"""
        logger.debug(f"Running command: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(f"Command failed: {result.stderr}")
            
            return result
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            raise
    
    def get_prometheus_metric(self, query: str) -> Optional[float]:
        """Get metric value from Prometheus"""
        try:
            response = requests.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data["status"] == "success" and data["data"]["result"]:
                    return float(data["data"]["result"][0]["value"][1])
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get metric '{query}': {str(e)}")
            return None
    
    def get_current_metrics(self) -> Optional[ScalingMetrics]:
        """Get current system metrics"""
        try:
            # Get CPU usage
            cpu_query = 'avg(100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100))'
            cpu_percent = self.get_prometheus_metric(cpu_query) or 0.0
            
            # Get memory usage
            memory_query = '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
            memory_percent = self.get_prometheus_metric(memory_query) or 0.0
            
            # Get response time (95th percentile)
            response_time_query = 'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="agents-unified"}[5m])) * 1000'
            response_time_ms = self.get_prometheus_metric(response_time_query) or 0.0
            
            # Get request rate
            request_rate_query = 'sum(rate(http_requests_total{job="agents-unified"}[5m]))'
            request_rate = self.get_prometheus_metric(request_rate_query) or 0.0
            
            # Get error rate
            error_rate_query = 'sum(rate(http_requests_total{job="agents-unified",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="agents-unified"}[5m])) * 100'
            error_rate = self.get_prometheus_metric(error_rate_query) or 0.0
            
            # Get current replica count
            current_replicas = self.get_current_replica_count()
            
            metrics = ScalingMetrics(
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                response_time_ms=response_time_ms,
                request_rate=request_rate,
                error_rate=error_rate,
                current_replicas=current_replicas,
                timestamp=datetime.now()
            )
            
            # Add to history
            self.metrics_history.append(metrics)
            
            # Keep only recent metrics
            cutoff_time = datetime.now() - timedelta(seconds=self.config.metrics_window)
            self.metrics_history = [
                m for m in self.metrics_history if m.timestamp > cutoff_time
            ]
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get current metrics: {str(e)}")
            return None
    
    def get_current_replica_count(self) -> int:
        """Get current number of replicas"""
        try:
            result = self.run_command([
                "docker-compose", "-f", self.compose_file,
                "ps", "-q", "agents-unified"
            ])
            
            if result.returncode == 0:
                containers = result.stdout.strip().split('\n')
                return len([c for c in containers if c.strip()])
            
            return 1
            
        except Exception as e:
            logger.warning(f"Failed to get replica count: {str(e)}")
            return 1
    
    def should_scale_up(self, metrics: ScalingMetrics) -> bool:
        """Determine if we should scale up"""
        if metrics.current_replicas >= self.config.max_replicas:
            return False
        
        # Check if we're in cooldown period
        if datetime.now() - self.last_scale_time < timedelta(seconds=self.config.cooldown_period):
            return False
        
        # Check scaling thresholds
        scale_up_conditions = [
            metrics.cpu_percent > self.config.target_cpu_percent * self.config.scale_up_threshold,
            metrics.memory_percent > self.config.target_memory_percent * self.config.scale_up_threshold,
            metrics.response_time_ms > self.config.target_response_time_ms * self.config.scale_up_threshold
        ]
        
        # Need at least 2 conditions to scale up
        return sum(scale_up_conditions) >= 2
    
    def should_scale_down(self, metrics: ScalingMetrics) -> bool:
        """Determine if we should scale down"""
        if metrics.current_replicas <= self.config.min_replicas:
            return False
        
        # Check if we're in cooldown period
        if datetime.now() - self.last_scale_time < timedelta(seconds=self.config.cooldown_period):
            return False
        
        # Check if metrics have been consistently low
        if len(self.metrics_history) < 3:
            return False
        
        recent_metrics = self.metrics_history[-3:]
        
        scale_down_conditions = []
        for m in recent_metrics:
            conditions = [
                m.cpu_percent < self.config.target_cpu_percent * self.config.scale_down_threshold,
                m.memory_percent < self.config.target_memory_percent * self.config.scale_down_threshold,
                m.response_time_ms < self.config.target_response_time_ms * self.config.scale_down_threshold
            ]
            scale_down_conditions.append(all(conditions))
        
        # All recent metrics must be low to scale down
        return all(scale_down_conditions)
    
    def scale_up(self, current_replicas: int) -> bool:
        """Scale up the deployment"""
        new_replicas = min(current_replicas + 1, self.config.max_replicas)
        
        logger.info(f"Scaling up from {current_replicas} to {new_replicas} replicas")
        
        try:
            result = self.run_command([
                "docker-compose", "-f", self.compose_file,
                "up", "-d", "--scale", f"agents-unified={new_replicas}"
            ])
            
            if result.returncode == 0:
                self.last_scale_time = datetime.now()
                logger.info(f"Successfully scaled up to {new_replicas} replicas")
                
                # Update load balancer if needed
                self.update_load_balancer(new_replicas)
                
                return True
            else:
                logger.error("Failed to scale up")
                return False
                
        except Exception as e:
            logger.error(f"Scale up failed: {str(e)}")
            return False
    
    def scale_down(self, current_replicas: int) -> bool:
        """Scale down the deployment"""
        new_replicas = max(current_replicas - 1, self.config.min_replicas)
        
        logger.info(f"Scaling down from {current_replicas} to {new_replicas} replicas")
        
        try:
            result = self.run_command([
                "docker-compose", "-f", self.compose_file,
                "up", "-d", "--scale", f"agents-unified={new_replicas}"
            ])
            
            if result.returncode == 0:
                self.last_scale_time = datetime.now()
                logger.info(f"Successfully scaled down to {new_replicas} replicas")
                
                # Update load balancer if needed
                self.update_load_balancer(new_replicas)
                
                return True
            else:
                logger.error("Failed to scale down")
                return False
                
        except Exception as e:
            logger.error(f"Scale down failed: {str(e)}")
            return False
    
    def update_load_balancer(self, replica_count: int) -> None:
        """Update load balancer configuration for new replica count"""
        try:
            # Check if nginx load balancer is running
            result = self.run_command([
                "docker", "ps", "-q", "-f", "name=agents-nginx-lb"
            ])
            
            if not result.stdout.strip():
                return  # No load balancer running
            
            # Generate new nginx config
            nginx_config = """
upstream agents_backend {
    least_conn;
"""
            
            for i in range(1, replica_count + 1):
                nginx_config += f"    server agents-unified_{i}:8000;\n"
            
            nginx_config += """
}

server {
    listen 80;
    server_name localhost;
    
    location / {
        proxy_pass http://agents_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    location /health {
        access_log off;
        proxy_pass http://agents_backend/health;
        proxy_set_header Host $host;
    }
}
"""
            
            # Write new config
            nginx_dir = Path("nginx")
            nginx_dir.mkdir(exist_ok=True)
            
            with open(nginx_dir / "nginx.conf", 'w') as f:
                f.write(nginx_config)
            
            # Reload nginx
            self.run_command([
                "docker", "exec", "agents-nginx-lb",
                "nginx", "-s", "reload"
            ])
            
            logger.info(f"Load balancer updated for {replica_count} replicas")
            
        except Exception as e:
            logger.warning(f"Failed to update load balancer: {str(e)}")
    
    def run_scaling_loop(self, check_interval: int = 30) -> None:
        """Run the auto-scaling loop"""
        logger.info("Starting auto-scaling loop...")
        logger.info(f"Config: min={self.config.min_replicas}, max={self.config.max_replicas}")
        logger.info(f"Targets: CPU={self.config.target_cpu_percent}%, Memory={self.config.target_memory_percent}%, Response={self.config.target_response_time_ms}ms")
        
        while True:
            try:
                # Get current metrics
                metrics = self.get_current_metrics()
                if not metrics:
                    logger.warning("Failed to get metrics, skipping scaling decision")
                    time.sleep(check_interval)
                    continue
                
                logger.info(f"Metrics: CPU={metrics.cpu_percent:.1f}%, Memory={metrics.memory_percent:.1f}%, "
                           f"Response={metrics.response_time_ms:.1f}ms, Replicas={metrics.current_replicas}")
                
                # Make scaling decision
                if self.should_scale_up(metrics):
                    self.scale_up(metrics.current_replicas)
                elif self.should_scale_down(metrics):
                    self.scale_down(metrics.current_replicas)
                else:
                    logger.debug("No scaling action needed")
                
                # Save metrics to file for monitoring
                self.save_scaling_metrics(metrics)
                
            except KeyboardInterrupt:
                logger.info("Auto-scaling stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in scaling loop: {str(e)}")
            
            time.sleep(check_interval)
    
    def save_scaling_metrics(self, metrics: ScalingMetrics) -> None:
        """Save scaling metrics to file"""
        try:
            metrics_dir = Path("monitoring/scaling_metrics")
            metrics_dir.mkdir(parents=True, exist_ok=True)
            
            metrics_file = metrics_dir / f"metrics_{datetime.now().strftime('%Y%m%d')}.jsonl"
            
            with open(metrics_file, 'a') as f:
                json.dump({
                    "timestamp": metrics.timestamp.isoformat(),
                    "cpu_percent": metrics.cpu_percent,
                    "memory_percent": metrics.memory_percent,
                    "response_time_ms": metrics.response_time_ms,
                    "request_rate": metrics.request_rate,
                    "error_rate": metrics.error_rate,
                    "current_replicas": metrics.current_replicas
                }, f)
                f.write('\n')
                
        except Exception as e:
            logger.warning(f"Failed to save metrics: {str(e)}")


def main():
    parser = argparse.ArgumentParser(description="Auto-scaling management for Autodesk Agents Unified")
    parser.add_argument("--environment", required=True, choices=["development", "production"])
    parser.add_argument("--min-replicas", type=int, default=1, help="Minimum number of replicas")
    parser.add_argument("--max-replicas", type=int, default=5, help="Maximum number of replicas")
    parser.add_argument("--target-cpu", type=float, default=70.0, help="Target CPU percentage")
    parser.add_argument("--target-memory", type=float, default=80.0, help="Target memory percentage")
    parser.add_argument("--target-response-time", type=float, default=2000.0, help="Target response time in ms")
    parser.add_argument("--scale-up-threshold", type=float, default=1.2, help="Scale up threshold multiplier")
    parser.add_argument("--scale-down-threshold", type=float, default=0.5, help="Scale down threshold multiplier")
    parser.add_argument("--cooldown-period", type=int, default=300, help="Cooldown period in seconds")
    parser.add_argument("--metrics-window", type=int, default=600, help="Metrics window in seconds")
    parser.add_argument("--check-interval", type=int, default=30, help="Check interval in seconds")
    parser.add_argument("--prometheus-url", help="Prometheus URL")
    
    args = parser.parse_args()
    
    if args.prometheus_url:
        os.environ["PROMETHEUS_URL"] = args.prometheus_url
    
    config = ScalingConfig(
        min_replicas=args.min_replicas,
        max_replicas=args.max_replicas,
        target_cpu_percent=args.target_cpu,
        target_memory_percent=args.target_memory,
        target_response_time_ms=args.target_response_time,
        scale_up_threshold=args.scale_up_threshold,
        scale_down_threshold=args.scale_down_threshold,
        cooldown_period=args.cooldown_period,
        metrics_window=args.metrics_window
    )
    
    scaler = AutoScaler(config, args.environment)
    scaler.run_scaling_loop(args.check_interval)
    
    return 0


if __name__ == "__main__":
    exit(main())