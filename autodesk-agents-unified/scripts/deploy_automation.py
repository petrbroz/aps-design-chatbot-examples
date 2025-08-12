#!/usr/bin/env python3
"""
Advanced deployment automation script for Autodesk Agents Unified
Provides comprehensive deployment, rollback, and monitoring capabilities
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class DeploymentConfig:
    """Configuration for deployment"""
    environment: str
    image_tag: str
    registry: Optional[str]
    health_check_url: str
    health_check_timeout: int
    rollback_enabled: bool
    backup_enabled: bool
    notification_webhook: Optional[str]
    scale_replicas: int = 1
    load_balancer_enabled: bool = False
    auto_scaling_enabled: bool = False
    min_replicas: int = 1
    max_replicas: int = 5


@dataclass
class DeploymentStatus:
    """Status of a deployment"""
    deployment_id: str
    environment: str
    image_tag: str
    status: str  # pending, deploying, healthy, failed, rolled_back
    start_time: datetime
    end_time: Optional[datetime]
    health_checks: List[Dict[str, Any]]
    errors: List[str]


class DeploymentManager:
    """Manages deployment lifecycle with advanced features"""
    
    def __init__(self, config: DeploymentConfig):
        self.config = config
        self.deployment_id = f"deploy-{int(time.time())}"
        self.status = DeploymentStatus(
            deployment_id=self.deployment_id,
            environment=config.environment,
            image_tag=config.image_tag,
            status="pending",
            start_time=datetime.now(),
            end_time=None,
            health_checks=[],
            errors=[]
        )
        
        # Create deployment directory
        self.deployment_dir = Path(f"deployments/{self.deployment_id}")
        self.deployment_dir.mkdir(parents=True, exist_ok=True)
    
    def save_deployment_state(self) -> None:
        """Save current deployment state to disk"""
        state_file = self.deployment_dir / "deployment_state.json"
        with open(state_file, 'w') as f:
            json.dump(asdict(self.status), f, indent=2, default=str)
    
    def load_deployment_state(self, deployment_id: str) -> Optional[DeploymentStatus]:
        """Load deployment state from disk"""
        state_file = Path(f"deployments/{deployment_id}/deployment_state.json")
        if not state_file.exists():
            return None
        
        with open(state_file, 'r') as f:
            data = json.load(f)
            return DeploymentStatus(**data)
    
    def run_command(self, command: List[str], capture_output: bool = True) -> subprocess.CompletedProcess:
        """Run a command with logging and error handling"""
        logger.info(f"Running command: {' '.join(command)}")
        
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                error_msg = f"Command failed with exit code {result.returncode}: {result.stderr}"
                logger.error(error_msg)
                self.status.errors.append(error_msg)
            
            return result
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            logger.error(error_msg)
            self.status.errors.append(error_msg)
            raise
    
    def backup_current_deployment(self) -> bool:
        """Create backup of current deployment"""
        if not self.config.backup_enabled:
            logger.info("Backup disabled, skipping...")
            return True
        
        logger.info("Creating deployment backup...")
        
        try:
            # Tag current image as backup
            backup_tag = f"backup-{int(time.time())}"
            
            # Check if current deployment exists
            result = self.run_command([
                "docker", "images", "-q", "autodesk-agents-unified:latest"
            ])
            
            if result.stdout.strip():
                # Tag current image as backup
                self.run_command([
                    "docker", "tag",
                    "autodesk-agents-unified:latest",
                    f"autodesk-agents-unified:{backup_tag}"
                ])
                
                # Save backup metadata
                backup_info = {
                    "backup_tag": backup_tag,
                    "original_tag": "latest",
                    "backup_time": datetime.now().isoformat(),
                    "deployment_id": self.deployment_id
                }
                
                backup_file = self.deployment_dir / "backup_info.json"
                with open(backup_file, 'w') as f:
                    json.dump(backup_info, f, indent=2)
                
                logger.info(f"Backup created with tag: {backup_tag}")
                return True
            else:
                logger.warning("No current deployment found to backup")
                return True
                
        except Exception as e:
            error_msg = f"Backup failed: {str(e)}"
            logger.error(error_msg)
            self.status.errors.append(error_msg)
            return False
    
    def build_and_push_image(self) -> bool:
        """Build and push Docker image"""
        logger.info(f"Building image with tag: {self.config.image_tag}")
        
        try:
            # Build image
            build_cmd = [
                "docker", "build",
                "--target", "production" if self.config.environment == "production" else "development",
                "--tag", f"autodesk-agents-unified:{self.config.image_tag}",
                "--tag", "autodesk-agents-unified:latest",
                "."
            ]
            
            result = self.run_command(build_cmd, capture_output=False)
            if result.returncode != 0:
                return False
            
            # Push to registry if configured
            if self.config.registry:
                registry_tag = f"{self.config.registry}/autodesk-agents-unified:{self.config.image_tag}"
                
                # Tag for registry
                self.run_command([
                    "docker", "tag",
                    f"autodesk-agents-unified:{self.config.image_tag}",
                    registry_tag
                ])
                
                # Push to registry
                result = self.run_command(["docker", "push", registry_tag])
                if result.returncode != 0:
                    return False
                
                logger.info(f"Image pushed to registry: {registry_tag}")
            
            return True
            
        except Exception as e:
            error_msg = f"Image build/push failed: {str(e)}"
            logger.error(error_msg)
            self.status.errors.append(error_msg)
            return False
    
    def deploy_services(self) -> bool:
        """Deploy services using Docker Compose with scaling support"""
        logger.info("Deploying services...")
        
        try:
            # Choose compose file based on environment
            compose_file = "docker-compose.prod.yml" if self.config.environment == "production" else "docker-compose.yml"
            
            # Stop existing services
            self.run_command([
                "docker-compose", "-f", compose_file,
                "down", "--remove-orphans"
            ])
            
            # Start new services with scaling
            deploy_cmd = [
                "docker-compose", "-f", compose_file,
                "up", "-d"
            ]
            
            # Add scaling if configured
            if self.config.scale_replicas > 1:
                deploy_cmd.extend([
                    "--scale", f"agents-unified={self.config.scale_replicas}"
                ])
                logger.info(f"Scaling to {self.config.scale_replicas} replicas")
            
            result = self.run_command(deploy_cmd)
            
            if result.returncode != 0:
                return False
            
            # Setup load balancer if enabled
            if self.config.load_balancer_enabled and self.config.scale_replicas > 1:
                if not self.setup_load_balancer():
                    logger.warning("Load balancer setup failed, continuing without it")
            
            logger.info("Services deployed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Service deployment failed: {str(e)}"
            logger.error(error_msg)
            self.status.errors.append(error_msg)
            return False
    
    def setup_load_balancer(self) -> bool:
        """Setup load balancer for scaled deployment"""
        logger.info("Setting up load balancer...")
        
        try:
            # Create nginx configuration for load balancing
            nginx_config = f"""
upstream agents_backend {{
    least_conn;
"""
            
            # Add backend servers
            for i in range(1, self.config.scale_replicas + 1):
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
        
        # Health check
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
            
            # Write nginx config
            nginx_dir = Path("nginx")
            nginx_dir.mkdir(exist_ok=True)
            
            with open(nginx_dir / "nginx.conf", 'w') as f:
                f.write(nginx_config)
            
            # Start nginx container
            result = self.run_command([
                "docker", "run", "-d",
                "--name", "agents-nginx-lb",
                "--network", "autodesk-agents-unified_default",
                "-p", "80:80",
                "-v", f"{nginx_dir.absolute()}/nginx.conf:/etc/nginx/conf.d/default.conf",
                "nginx:alpine"
            ])
            
            if result.returncode == 0:
                logger.info("Load balancer configured successfully")
                return True
            else:
                logger.error("Failed to start load balancer")
                return False
                
        except Exception as e:
            logger.error(f"Load balancer setup failed: {str(e)}")
            return False
    
    def run_health_checks(self) -> bool:
        """Run comprehensive health checks"""
        logger.info("Running health checks...")
        
        max_attempts = self.config.health_check_timeout // 5
        
        for attempt in range(max_attempts):
            try:
                # Basic health check
                response = requests.get(
                    self.config.health_check_url,
                    timeout=10
                )
                
                health_check = {
                    "attempt": attempt + 1,
                    "timestamp": datetime.now().isoformat(),
                    "status_code": response.status_code,
                    "response_time": response.elapsed.total_seconds(),
                    "healthy": response.status_code == 200
                }
                
                self.status.health_checks.append(health_check)
                
                if response.status_code == 200:
                    # Additional checks for production
                    if self.config.environment == "production":
                        if not self.run_extended_health_checks():
                            continue
                    
                    logger.info("Health checks passed")
                    return True
                
                logger.warning(f"Health check failed (attempt {attempt + 1}/{max_attempts}): HTTP {response.status_code}")
                
            except requests.RequestException as e:
                health_check = {
                    "attempt": attempt + 1,
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e),
                    "healthy": False
                }
                
                self.status.health_checks.append(health_check)
                logger.warning(f"Health check failed (attempt {attempt + 1}/{max_attempts}): {str(e)}")
            
            if attempt < max_attempts - 1:
                time.sleep(5)
        
        error_msg = "Health checks failed after all attempts"
        logger.error(error_msg)
        self.status.errors.append(error_msg)
        return False
    
    def run_extended_health_checks(self) -> bool:
        """Run extended health checks for production deployments"""
        logger.info("Running extended health checks...")
        
        checks = [
            ("/health/agents", "Agent health check"),
            ("/health/dependencies", "Dependencies health check"),
            ("/metrics", "Metrics endpoint check")
        ]
        
        for endpoint, description in checks:
            try:
                url = self.config.health_check_url.replace("/health", endpoint)
                response = requests.get(url, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"{description} failed: HTTP {response.status_code}")
                    return False
                
                logger.info(f"{description} passed")
                
            except requests.RequestException as e:
                logger.warning(f"{description} failed: {str(e)}")
                return False
        
        return True
    
    def send_notification(self, message: str, status: str = "info") -> None:
        """Send deployment notification"""
        if not self.config.notification_webhook:
            return
        
        try:
            payload = {
                "deployment_id": self.deployment_id,
                "environment": self.config.environment,
                "status": status,
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            
            requests.post(
                self.config.notification_webhook,
                json=payload,
                timeout=10
            )
            
        except Exception as e:
            logger.warning(f"Failed to send notification: {str(e)}")
    
    def rollback_deployment(self) -> bool:
        """Rollback to previous deployment"""
        if not self.config.rollback_enabled:
            logger.error("Rollback is disabled")
            return False
        
        logger.info("Rolling back deployment...")
        
        try:
            # Load backup info
            backup_file = self.deployment_dir / "backup_info.json"
            if not backup_file.exists():
                logger.error("No backup information found")
                return False
            
            with open(backup_file, 'r') as f:
                backup_info = json.load(f)
            
            backup_tag = backup_info["backup_tag"]
            
            # Tag backup as latest
            self.run_command([
                "docker", "tag",
                f"autodesk-agents-unified:{backup_tag}",
                "autodesk-agents-unified:latest"
            ])
            
            # Redeploy with backup image
            if not self.deploy_services():
                return False
            
            # Run health checks
            if not self.run_health_checks():
                logger.error("Rollback health checks failed")
                return False
            
            self.status.status = "rolled_back"
            logger.info("Rollback completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Rollback failed: {str(e)}"
            logger.error(error_msg)
            self.status.errors.append(error_msg)
            return False
    
    def deploy(self) -> bool:
        """Run complete deployment process"""
        logger.info(f"Starting deployment {self.deployment_id}")
        self.status.status = "deploying"
        self.save_deployment_state()
        
        try:
            # Send start notification
            self.send_notification(f"Deployment {self.deployment_id} started", "info")
            
            # Create backup
            if not self.backup_current_deployment():
                self.status.status = "failed"
                self.save_deployment_state()
                self.send_notification("Backup failed", "error")
                return False
            
            # Build and push image
            if not self.build_and_push_image():
                self.status.status = "failed"
                self.save_deployment_state()
                self.send_notification("Image build failed", "error")
                return False
            
            # Deploy services
            if not self.deploy_services():
                self.status.status = "failed"
                self.save_deployment_state()
                self.send_notification("Service deployment failed", "error")
                
                # Auto-rollback if enabled
                if self.config.rollback_enabled:
                    self.rollback_deployment()
                
                return False
            
            # Run health checks
            if not self.run_health_checks():
                self.status.status = "failed"
                self.save_deployment_state()
                self.send_notification("Health checks failed", "error")
                
                # Auto-rollback if enabled
                if self.config.rollback_enabled:
                    self.rollback_deployment()
                
                return False
            
            # Success
            self.status.status = "healthy"
            self.status.end_time = datetime.now()
            self.save_deployment_state()
            
            duration = (self.status.end_time - self.status.start_time).total_seconds()
            self.send_notification(f"Deployment {self.deployment_id} completed successfully in {duration:.1f}s", "success")
            
            logger.info(f"Deployment {self.deployment_id} completed successfully")
            return True
            
        except Exception as e:
            error_msg = f"Deployment failed: {str(e)}"
            logger.error(error_msg)
            self.status.errors.append(error_msg)
            self.status.status = "failed"
            self.status.end_time = datetime.now()
            self.save_deployment_state()
            
            self.send_notification(f"Deployment {self.deployment_id} failed: {str(e)}", "error")
            return False


def main():
    parser = argparse.ArgumentParser(description="Advanced deployment automation")
    parser.add_argument("--environment", required=True, choices=["development", "production"])
    parser.add_argument("--image-tag", default="latest")
    parser.add_argument("--registry", help="Docker registry URL")
    parser.add_argument("--health-check-url", default="http://localhost:8000/health")
    parser.add_argument("--health-check-timeout", type=int, default=300)
    parser.add_argument("--no-rollback", action="store_true", help="Disable auto-rollback")
    parser.add_argument("--no-backup", action="store_true", help="Disable backup creation")
    parser.add_argument("--notification-webhook", help="Webhook URL for notifications")
    parser.add_argument("--rollback", help="Rollback to specific deployment ID")
    parser.add_argument("--scale", type=int, default=1, help="Number of replicas to deploy")
    parser.add_argument("--enable-load-balancer", action="store_true", help="Enable load balancer for scaled deployments")
    parser.add_argument("--enable-auto-scaling", action="store_true", help="Enable auto-scaling (production only)")
    parser.add_argument("--min-replicas", type=int, default=1, help="Minimum replicas for auto-scaling")
    parser.add_argument("--max-replicas", type=int, default=5, help="Maximum replicas for auto-scaling")
    
    args = parser.parse_args()
    
    # Handle rollback command
    if args.rollback:
        config = DeploymentConfig(
            environment=args.environment,
            image_tag=args.image_tag,
            registry=args.registry,
            health_check_url=args.health_check_url,
            health_check_timeout=args.health_check_timeout,
            rollback_enabled=True,
            backup_enabled=not args.no_backup,
            notification_webhook=args.notification_webhook
        )
        
        manager = DeploymentManager(config)
        manager.deployment_id = args.rollback
        manager.deployment_dir = Path(f"deployments/{args.rollback}")
        
        if manager.rollback_deployment():
            print(f"Rollback to {args.rollback} completed successfully")
            return 0
        else:
            print(f"Rollback to {args.rollback} failed")
            return 1
    
    # Regular deployment
    config = DeploymentConfig(
        environment=args.environment,
        image_tag=args.image_tag,
        registry=args.registry,
        health_check_url=args.health_check_url,
        health_check_timeout=args.health_check_timeout,
        rollback_enabled=not args.no_rollback,
        backup_enabled=not args.no_backup,
        notification_webhook=args.notification_webhook,
        scale_replicas=args.scale,
        load_balancer_enabled=args.enable_load_balancer,
        auto_scaling_enabled=args.enable_auto_scaling and args.environment == "production",
        min_replicas=args.min_replicas,
        max_replicas=args.max_replicas
    )
    
    manager = DeploymentManager(config)
    
    if manager.deploy():
        print(f"Deployment {manager.deployment_id} completed successfully")
        return 0
    else:
        print(f"Deployment {manager.deployment_id} failed")
        return 1


if __name__ == "__main__":
    exit(main())