#!/usr/bin/env python3
"""
Deployment status dashboard for Autodesk Agents Unified
Provides real-time status of deployments, health, and system metrics
"""

import os
import json
import time
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
class SystemStatus:
    """System status information"""
    timestamp: datetime
    overall_health: str
    agents_status: Dict[str, str]
    dependencies_status: Dict[str, str]
    metrics: Dict[str, float]
    active_deployments: List[Dict[str, Any]]
    recent_alerts: List[Dict[str, Any]]


class DeploymentStatusDashboard:
    """Provides deployment status and monitoring dashboard"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.prometheus_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
        self.deployments_dir = Path("deployments")
        self.monitoring_dir = Path("monitoring")
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            if response.status_code == 200:
                return {"status": "healthy", "data": response.json()}
            else:
                return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}
    
    def get_agents_status(self) -> Dict[str, str]:
        """Get status of all agents"""
        try:
            response = requests.get(f"{self.base_url}/health/agents", timeout=10)
            if response.status_code == 200:
                data = response.json()
                agents_status = {}
                
                if "agents" in data:
                    for agent in data["agents"]:
                        agent_type = agent.get("type", "unknown")
                        status = agent.get("status", "unknown")
                        agents_status[agent_type] = status
                
                return agents_status
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_dependencies_status(self) -> Dict[str, str]:
        """Get status of system dependencies"""
        try:
            response = requests.get(f"{self.base_url}/health/dependencies", timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get("dependencies", {})
            else:
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}
    
    def get_prometheus_metric(self, query: str) -> Optional[float]:
        """Get metric from Prometheus"""
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
        except Exception:
            return None
    
    def get_system_metrics(self) -> Dict[str, float]:
        """Get key system metrics"""
        metrics = {}
        
        # Request rate
        request_rate = self.get_prometheus_metric(
            'sum(rate(http_requests_total{job="agents-unified"}[5m]))'
        )
        if request_rate is not None:
            metrics["request_rate"] = request_rate
        
        # Response time (95th percentile)
        response_time = self.get_prometheus_metric(
            'histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{job="agents-unified"}[5m])) * 1000'
        )
        if response_time is not None:
            metrics["response_time_p95"] = response_time
        
        # Error rate
        error_rate = self.get_prometheus_metric(
            'sum(rate(http_requests_total{job="agents-unified",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="agents-unified"}[5m])) * 100'
        )
        if error_rate is not None:
            metrics["error_rate"] = error_rate
        
        # CPU usage
        cpu_usage = self.get_prometheus_metric(
            'avg(100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100))'
        )
        if cpu_usage is not None:
            metrics["cpu_usage"] = cpu_usage
        
        # Memory usage
        memory_usage = self.get_prometheus_metric(
            '(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100'
        )
        if memory_usage is not None:
            metrics["memory_usage"] = memory_usage
        
        return metrics
    
    def get_active_deployments(self) -> List[Dict[str, Any]]:
        """Get list of active deployments"""
        deployments = []
        
        if not self.deployments_dir.exists():
            return deployments
        
        for deployment_dir in self.deployments_dir.iterdir():
            if not deployment_dir.is_dir():
                continue
            
            state_file = deployment_dir / "deployment_state.json"
            if not state_file.exists():
                continue
            
            try:
                with open(state_file, 'r') as f:
                    deployment_data = json.load(f)
                    
                # Only include recent deployments
                start_time = datetime.fromisoformat(deployment_data.get('start_time', ''))
                if datetime.now() - start_time < timedelta(days=7):
                    deployments.append(deployment_data)
                    
            except Exception as e:
                logger.warning(f"Failed to read deployment {deployment_dir}: {e}")
        
        # Sort by start time (newest first)
        deployments.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        return deployments[:10]  # Return last 10 deployments
    
    def get_recent_alerts(self) -> List[Dict[str, Any]]:
        """Get recent alerts from Alertmanager"""
        alerts = []
        
        try:
            alertmanager_url = os.getenv("ALERTMANAGER_URL", "http://localhost:9093")
            response = requests.get(f"{alertmanager_url}/api/v1/alerts", timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    for alert in data["data"]:
                        alerts.append({
                            "name": alert.get("labels", {}).get("alertname", "Unknown"),
                            "severity": alert.get("labels", {}).get("severity", "unknown"),
                            "status": alert.get("status", {}).get("state", "unknown"),
                            "starts_at": alert.get("startsAt", ""),
                            "summary": alert.get("annotations", {}).get("summary", "")
                        })
        except Exception as e:
            logger.warning(f"Failed to get alerts: {e}")
        
        return alerts[:5]  # Return last 5 alerts
    
    def get_docker_containers_status(self) -> Dict[str, str]:
        """Get status of Docker containers"""
        containers = {}
        
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}"],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')[1:]  # Skip header
                for line in lines:
                    if '\t' in line:
                        name, status = line.split('\t', 1)
                        containers[name] = status
                        
        except Exception as e:
            logger.warning(f"Failed to get container status: {e}")
        
        return containers
    
    def collect_status(self) -> SystemStatus:
        """Collect comprehensive system status"""
        logger.info("Collecting system status...")
        
        system_health = self.get_system_health()
        agents_status = self.get_agents_status()
        dependencies_status = self.get_dependencies_status()
        metrics = self.get_system_metrics()
        active_deployments = self.get_active_deployments()
        recent_alerts = self.get_recent_alerts()
        
        overall_health = system_health.get("status", "unknown")
        
        return SystemStatus(
            timestamp=datetime.now(),
            overall_health=overall_health,
            agents_status=agents_status,
            dependencies_status=dependencies_status,
            metrics=metrics,
            active_deployments=active_deployments,
            recent_alerts=recent_alerts
        )
    
    def print_status_dashboard(self, status: SystemStatus) -> None:
        """Print formatted status dashboard"""
        print("\n" + "="*80)
        print("🚀 AUTODESK AGENTS UNIFIED - DEPLOYMENT STATUS DASHBOARD")
        print("="*80)
        print(f"📅 Timestamp: {status.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🏥 Overall Health: {self._format_status(status.overall_health)}")
        
        # Agents Status
        print("\n📊 AGENTS STATUS")
        print("-" * 40)
        if isinstance(status.agents_status, dict) and not status.agents_status.get("error"):
            for agent, agent_status in status.agents_status.items():
                print(f"  {agent:20} {self._format_status(agent_status)}")
        else:
            print(f"  ❌ Error: {status.agents_status.get('error', 'Unknown error')}")
        
        # Dependencies Status
        print("\n🔗 DEPENDENCIES STATUS")
        print("-" * 40)
        if isinstance(status.dependencies_status, dict) and not status.dependencies_status.get("error"):
            for dep, dep_status in status.dependencies_status.items():
                print(f"  {dep:20} {self._format_status(dep_status)}")
        else:
            print(f"  ❌ Error: {status.dependencies_status.get('error', 'Unknown error')}")
        
        # System Metrics
        print("\n📈 SYSTEM METRICS")
        print("-" * 40)
        if status.metrics:
            for metric, value in status.metrics.items():
                formatted_value = self._format_metric(metric, value)
                print(f"  {metric:20} {formatted_value}")
        else:
            print("  ⚠️  No metrics available")
        
        # Active Deployments
        print("\n🚢 RECENT DEPLOYMENTS")
        print("-" * 40)
        if status.active_deployments:
            for deployment in status.active_deployments[:5]:
                deploy_id = deployment.get('deployment_id', 'unknown')[:20]
                deploy_status = deployment.get('status', 'unknown')
                start_time = deployment.get('start_time', '')[:19]  # Remove microseconds
                print(f"  {deploy_id:20} {self._format_status(deploy_status):15} {start_time}")
        else:
            print("  📭 No recent deployments")
        
        # Recent Alerts
        print("\n🚨 RECENT ALERTS")
        print("-" * 40)
        if status.recent_alerts:
            for alert in status.recent_alerts:
                name = alert.get('name', 'Unknown')[:25]
                severity = alert.get('severity', 'unknown')
                alert_status = alert.get('status', 'unknown')
                print(f"  {name:25} {self._format_severity(severity):10} {alert_status}")
        else:
            print("  ✅ No active alerts")
        
        # Docker Containers
        containers = self.get_docker_containers_status()
        if containers:
            print("\n🐳 DOCKER CONTAINERS")
            print("-" * 40)
            for name, container_status in containers.items():
                if 'agents' in name.lower() or 'prometheus' in name.lower() or 'grafana' in name.lower():
                    status_short = container_status.split()[0] if container_status else "unknown"
                    print(f"  {name:25} {self._format_status(status_short)}")
        
        print("\n" + "="*80)
    
    def _format_status(self, status: str) -> str:
        """Format status with colors"""
        status_lower = status.lower()
        if status_lower in ['healthy', 'up', 'running', 'passed', 'completed']:
            return f"✅ {status}"
        elif status_lower in ['unhealthy', 'down', 'failed', 'error']:
            return f"❌ {status}"
        elif status_lower in ['warning', 'degraded', 'pending']:
            return f"⚠️  {status}"
        else:
            return f"❓ {status}"
    
    def _format_severity(self, severity: str) -> str:
        """Format alert severity with colors"""
        severity_lower = severity.lower()
        if severity_lower == 'critical':
            return f"🔴 {severity}"
        elif severity_lower == 'warning':
            return f"🟡 {severity}"
        elif severity_lower == 'info':
            return f"🔵 {severity}"
        else:
            return f"⚪ {severity}"
    
    def _format_metric(self, metric: str, value: float) -> str:
        """Format metric values"""
        if 'rate' in metric:
            return f"{value:.2f} req/s"
        elif 'time' in metric:
            return f"{value:.1f} ms"
        elif 'usage' in metric or 'percent' in metric:
            return f"{value:.1f}%"
        else:
            return f"{value:.2f}"
    
    def save_status_json(self, status: SystemStatus, output_file: str) -> None:
        """Save status to JSON file"""
        try:
            status_dict = {
                "timestamp": status.timestamp.isoformat(),
                "overall_health": status.overall_health,
                "agents_status": status.agents_status,
                "dependencies_status": status.dependencies_status,
                "metrics": status.metrics,
                "active_deployments": status.active_deployments,
                "recent_alerts": status.recent_alerts
            }
            
            with open(output_file, 'w') as f:
                json.dump(status_dict, f, indent=2)
            
            logger.info(f"Status saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save status: {e}")
    
    def run_continuous_monitoring(self, interval: int = 30) -> None:
        """Run continuous monitoring dashboard"""
        logger.info(f"Starting continuous monitoring (refresh every {interval}s)")
        logger.info("Press Ctrl+C to stop")
        
        try:
            while True:
                # Clear screen (works on most terminals)
                os.system('clear' if os.name == 'posix' else 'cls')
                
                status = self.collect_status()
                self.print_status_dashboard(status)
                
                print(f"\n🔄 Refreshing in {interval} seconds... (Press Ctrl+C to stop)")
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\n👋 Monitoring stopped by user")


def main():
    parser = argparse.ArgumentParser(description="Deployment status dashboard")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL of the service")
    parser.add_argument("--output", help="Save status to JSON file")
    parser.add_argument("--continuous", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--interval", type=int, default=30, help="Refresh interval for continuous mode")
    parser.add_argument("--prometheus-url", help="Prometheus URL")
    parser.add_argument("--alertmanager-url", help="Alertmanager URL")
    
    args = parser.parse_args()
    
    if args.prometheus_url:
        os.environ["PROMETHEUS_URL"] = args.prometheus_url
    
    if args.alertmanager_url:
        os.environ["ALERTMANAGER_URL"] = args.alertmanager_url
    
    dashboard = DeploymentStatusDashboard(args.base_url)
    
    if args.continuous:
        dashboard.run_continuous_monitoring(args.interval)
    else:
        status = dashboard.collect_status()
        dashboard.print_status_dashboard(status)
        
        if args.output:
            dashboard.save_status_json(status, args.output)
    
    return 0


if __name__ == "__main__":
    exit(main())