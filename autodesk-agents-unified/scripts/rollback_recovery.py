#!/usr/bin/env python3
"""
Rollback and recovery script for Autodesk Agents Unified
Provides comprehensive rollback capabilities and disaster recovery procedures
"""

import os
import json
import time
import logging
import argparse
import subprocess
import shutil
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
class BackupInfo:
    """Information about a backup"""
    backup_id: str
    timestamp: datetime
    environment: str
    image_tag: str
    deployment_id: str
    backup_type: str  # full, incremental, emergency
    size_bytes: int
    status: str  # created, verified, corrupted, restored


@dataclass
class RecoveryPlan:
    """Recovery plan configuration"""
    recovery_type: str  # rollback, restore, rebuild
    target_backup: str
    estimated_downtime: int
    verification_steps: List[str]
    rollback_steps: List[str]


class RollbackManager:
    """Manages rollback and recovery operations"""
    
    def __init__(self, environment: str):
        self.environment = environment
        self.backups_dir = Path("backups")
        self.deployments_dir = Path("deployments")
        self.recovery_dir = Path("recovery")
        
        # Create directories
        for directory in [self.backups_dir, self.deployments_dir, self.recovery_dir]:
            directory.mkdir(exist_ok=True)
    
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
                logger.error(f"Command failed with exit code {result.returncode}: {result.stderr}")
            
            return result
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}")
            raise
    
    def list_deployments(self) -> List[Dict[str, Any]]:
        """List all available deployments"""
        deployments = []
        
        for deployment_dir in self.deployments_dir.iterdir():
            if not deployment_dir.is_dir():
                continue
            
            state_file = deployment_dir / "deployment_state.json"
            if not state_file.exists():
                continue
            
            try:
                with open(state_file, 'r') as f:
                    deployment_data = json.load(f)
                    deployments.append(deployment_data)
            except Exception as e:
                logger.warning(f"Failed to read deployment state {deployment_dir}: {e}")
        
        # Sort by start time (newest first)
        deployments.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        return deployments
    
    def list_backups(self) -> List[BackupInfo]:
        """List all available backups"""
        backups = []
        
        for backup_dir in self.backups_dir.iterdir():
            if not backup_dir.is_dir():
                continue
            
            backup_file = backup_dir / "backup_info.json"
            if not backup_file.exists():
                continue
            
            try:
                with open(backup_file, 'r') as f:
                    backup_data = json.load(f)
                    
                backup_info = BackupInfo(
                    backup_id=backup_data.get('backup_id', backup_dir.name),
                    timestamp=datetime.fromisoformat(backup_data.get('timestamp', datetime.now().isoformat())),
                    environment=backup_data.get('environment', 'unknown'),
                    image_tag=backup_data.get('image_tag', 'unknown'),
                    deployment_id=backup_data.get('deployment_id', 'unknown'),
                    backup_type=backup_data.get('backup_type', 'full'),
                    size_bytes=backup_data.get('size_bytes', 0),
                    status=backup_data.get('status', 'unknown')
                )
                
                backups.append(backup_info)
                
            except Exception as e:
                logger.warning(f"Failed to read backup info {backup_dir}: {e}")
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x.timestamp, reverse=True)
        return backups
    
    def create_emergency_backup(self) -> Optional[str]:
        """Create an emergency backup before rollback"""
        logger.info("Creating emergency backup...")
        
        backup_id = f"emergency-{int(time.time())}"
        backup_dir = self.backups_dir / backup_id
        backup_dir.mkdir(exist_ok=True)
        
        try:
            # Backup current Docker images
            logger.info("Backing up Docker images...")
            
            # Get current image ID
            result = self.run_command([
                "docker", "images", "-q", "autodesk-agents-unified:latest"
            ])
            
            if result.stdout.strip():
                image_id = result.stdout.strip()
                
                # Save image to tar file
                image_file = backup_dir / "image.tar"
                result = self.run_command([
                    "docker", "save", "-o", str(image_file), "autodesk-agents-unified:latest"
                ])
                
                if result.returncode != 0:
                    logger.error("Failed to save Docker image")
                    return None
            
            # Backup configuration files
            logger.info("Backing up configuration...")
            config_backup_dir = backup_dir / "config"
            config_backup_dir.mkdir(exist_ok=True)
            
            config_dir = Path("config")
            if config_dir.exists():
                shutil.copytree(config_dir, config_backup_dir / "config", dirs_exist_ok=True)
            
            # Backup cache data
            logger.info("Backing up cache data...")
            cache_backup_dir = backup_dir / "cache"
            cache_backup_dir.mkdir(exist_ok=True)
            
            cache_dirs = ["dev_cache", "cache"]
            for cache_dir_name in cache_dirs:
                cache_dir = Path(cache_dir_name)
                if cache_dir.exists():
                    shutil.copytree(cache_dir, cache_backup_dir / cache_dir_name, dirs_exist_ok=True)
            
            # Create backup metadata
            backup_info = {
                "backup_id": backup_id,
                "timestamp": datetime.now().isoformat(),
                "environment": self.environment,
                "image_tag": "latest",
                "deployment_id": "current",
                "backup_type": "emergency",
                "size_bytes": self._calculate_backup_size(backup_dir),
                "status": "created"
            }
            
            backup_file = backup_dir / "backup_info.json"
            with open(backup_file, 'w') as f:
                json.dump(backup_info, f, indent=2)
            
            logger.info(f"Emergency backup created: {backup_id}")
            return backup_id
            
        except Exception as e:
            logger.error(f"Emergency backup failed: {str(e)}")
            # Clean up failed backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            return None
    
    def _calculate_backup_size(self, backup_dir: Path) -> int:
        """Calculate total size of backup directory"""
        total_size = 0
        for file_path in backup_dir.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size
    
    def rollback_to_deployment(self, deployment_id: str) -> bool:
        """Rollback to a specific deployment"""
        logger.info(f"Rolling back to deployment: {deployment_id}")
        
        # Find deployment info
        deployment_dir = self.deployments_dir / deployment_id
        if not deployment_dir.exists():
            logger.error(f"Deployment {deployment_id} not found")
            return False
        
        state_file = deployment_dir / "deployment_state.json"
        if not state_file.exists():
            logger.error(f"Deployment state file not found for {deployment_id}")
            return False
        
        try:
            with open(state_file, 'r') as f:
                deployment_data = json.load(f)
            
            image_tag = deployment_data.get('image_tag', 'latest')
            
            # Check if backup exists
            backup_file = deployment_dir / "backup_info.json"
            if not backup_file.exists():
                logger.error(f"No backup found for deployment {deployment_id}")
                return False
            
            with open(backup_file, 'r') as f:
                backup_data = json.load(f)
            
            backup_tag = backup_data.get('backup_tag')
            if not backup_tag:
                logger.error(f"Invalid backup data for deployment {deployment_id}")
                return False
            
            # Create emergency backup of current state
            emergency_backup = self.create_emergency_backup()
            if not emergency_backup:
                logger.warning("Failed to create emergency backup, continuing with rollback...")
            
            # Stop current services
            logger.info("Stopping current services...")
            compose_file = "docker-compose.prod.yml" if self.environment == "production" else "docker-compose.yml"
            
            result = self.run_command([
                "docker-compose", "-f", compose_file, "down"
            ])
            
            if result.returncode != 0:
                logger.error("Failed to stop current services")
                return False
            
            # Restore backup image
            logger.info(f"Restoring image with tag: {backup_tag}")
            
            # Check if backup image exists
            result = self.run_command([
                "docker", "images", "-q", f"autodesk-agents-unified:{backup_tag}"
            ])
            
            if not result.stdout.strip():
                logger.error(f"Backup image not found: {backup_tag}")
                return False
            
            # Tag backup image as latest
            result = self.run_command([
                "docker", "tag",
                f"autodesk-agents-unified:{backup_tag}",
                "autodesk-agents-unified:latest"
            ])
            
            if result.returncode != 0:
                logger.error("Failed to tag backup image")
                return False
            
            # Start services with restored image
            logger.info("Starting services with restored image...")
            result = self.run_command([
                "docker-compose", "-f", compose_file, "up", "-d"
            ])
            
            if result.returncode != 0:
                logger.error("Failed to start services")
                return False
            
            # Wait for services to be ready
            logger.info("Waiting for services to be ready...")
            time.sleep(30)
            
            # Run health checks
            if not self._run_rollback_health_checks():
                logger.error("Rollback health checks failed")
                return False
            
            # Create rollback record
            rollback_record = {
                "rollback_id": f"rollback-{int(time.time())}",
                "timestamp": datetime.now().isoformat(),
                "source_deployment": deployment_id,
                "target_image": backup_tag,
                "emergency_backup": emergency_backup,
                "status": "completed"
            }
            
            rollback_file = self.recovery_dir / f"rollback-{int(time.time())}.json"
            with open(rollback_file, 'w') as f:
                json.dump(rollback_record, f, indent=2)
            
            logger.info(f"Rollback to {deployment_id} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            return False
    
    def restore_from_backup(self, backup_id: str) -> bool:
        """Restore system from a specific backup"""
        logger.info(f"Restoring from backup: {backup_id}")
        
        backup_dir = self.backups_dir / backup_id
        if not backup_dir.exists():
            logger.error(f"Backup {backup_id} not found")
            return False
        
        try:
            # Load backup info
            backup_file = backup_dir / "backup_info.json"
            with open(backup_file, 'r') as f:
                backup_info = json.load(f)
            
            # Create emergency backup
            emergency_backup = self.create_emergency_backup()
            
            # Stop current services
            logger.info("Stopping current services...")
            compose_file = "docker-compose.prod.yml" if self.environment == "production" else "docker-compose.yml"
            
            self.run_command([
                "docker-compose", "-f", compose_file, "down"
            ])
            
            # Restore Docker image
            image_file = backup_dir / "image.tar"
            if image_file.exists():
                logger.info("Restoring Docker image...")
                result = self.run_command([
                    "docker", "load", "-i", str(image_file)
                ])
                
                if result.returncode != 0:
                    logger.error("Failed to restore Docker image")
                    return False
            
            # Restore configuration
            config_backup_dir = backup_dir / "config" / "config"
            if config_backup_dir.exists():
                logger.info("Restoring configuration...")
                config_dir = Path("config")
                if config_dir.exists():
                    shutil.rmtree(config_dir)
                shutil.copytree(config_backup_dir, config_dir)
            
            # Restore cache data
            cache_backup_dir = backup_dir / "cache"
            if cache_backup_dir.exists():
                logger.info("Restoring cache data...")
                for cache_dir_name in ["dev_cache", "cache"]:
                    cache_source = cache_backup_dir / cache_dir_name
                    if cache_source.exists():
                        cache_target = Path(cache_dir_name)
                        if cache_target.exists():
                            shutil.rmtree(cache_target)
                        shutil.copytree(cache_source, cache_target)
            
            # Start services
            logger.info("Starting restored services...")
            result = self.run_command([
                "docker-compose", "-f", compose_file, "up", "-d"
            ])
            
            if result.returncode != 0:
                logger.error("Failed to start restored services")
                return False
            
            # Wait and run health checks
            logger.info("Waiting for services to be ready...")
            time.sleep(30)
            
            if not self._run_rollback_health_checks():
                logger.error("Restore health checks failed")
                return False
            
            # Create restore record
            restore_record = {
                "restore_id": f"restore-{int(time.time())}",
                "timestamp": datetime.now().isoformat(),
                "source_backup": backup_id,
                "emergency_backup": emergency_backup,
                "status": "completed"
            }
            
            restore_file = self.recovery_dir / f"restore-{int(time.time())}.json"
            with open(restore_file, 'w') as f:
                json.dump(restore_record, f, indent=2)
            
            logger.info(f"Restore from backup {backup_id} completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Restore failed: {str(e)}")
            return False
    
    def _run_rollback_health_checks(self) -> bool:
        """Run health checks after rollback/restore"""
        logger.info("Running post-rollback health checks...")
        
        max_attempts = 10
        for attempt in range(max_attempts):
            try:
                import requests
                response = requests.get("http://localhost:8000/health", timeout=10)
                
                if response.status_code == 200:
                    logger.info("Basic health check passed")
                    
                    # Additional checks
                    endpoints = ["/health/agents", "/health/dependencies"]
                    for endpoint in endpoints:
                        try:
                            resp = requests.get(f"http://localhost:8000{endpoint}", timeout=10)
                            if resp.status_code == 200:
                                logger.info(f"Health check passed: {endpoint}")
                            else:
                                logger.warning(f"Health check warning: {endpoint} returned {resp.status_code}")
                        except Exception as e:
                            logger.warning(f"Health check warning: {endpoint} failed: {e}")
                    
                    return True
                
                logger.warning(f"Health check failed (attempt {attempt + 1}/{max_attempts}): HTTP {response.status_code}")
                
            except Exception as e:
                logger.warning(f"Health check failed (attempt {attempt + 1}/{max_attempts}): {str(e)}")
            
            if attempt < max_attempts - 1:
                time.sleep(10)
        
        return False
    
    def cleanup_old_backups(self, keep_count: int = 10) -> None:
        """Clean up old backups, keeping only the most recent ones"""
        logger.info(f"Cleaning up old backups, keeping {keep_count} most recent...")
        
        backups = self.list_backups()
        
        if len(backups) <= keep_count:
            logger.info(f"Only {len(backups)} backups found, no cleanup needed")
            return
        
        backups_to_remove = backups[keep_count:]
        
        for backup in backups_to_remove:
            backup_dir = self.backups_dir / backup.backup_id
            if backup_dir.exists():
                try:
                    shutil.rmtree(backup_dir)
                    logger.info(f"Removed old backup: {backup.backup_id}")
                except Exception as e:
                    logger.warning(f"Failed to remove backup {backup.backup_id}: {e}")
        
        logger.info(f"Cleanup completed, removed {len(backups_to_remove)} old backups")


def main():
    parser = argparse.ArgumentParser(description="Rollback and recovery management")
    parser.add_argument("--environment", required=True, choices=["development", "production"])
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # List commands
    list_parser = subparsers.add_parser("list", help="List deployments or backups")
    list_parser.add_argument("type", choices=["deployments", "backups"])
    
    # Rollback command
    rollback_parser = subparsers.add_parser("rollback", help="Rollback to deployment")
    rollback_parser.add_argument("deployment_id", help="Deployment ID to rollback to")
    
    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore from backup")
    restore_parser.add_argument("backup_id", help="Backup ID to restore from")
    
    # Backup command
    backup_parser = subparsers.add_parser("backup", help="Create emergency backup")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up old backups")
    cleanup_parser.add_argument("--keep", type=int, default=10, help="Number of backups to keep")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    manager = RollbackManager(args.environment)
    
    if args.command == "list":
        if args.type == "deployments":
            deployments = manager.list_deployments()
            print(f"\nFound {len(deployments)} deployments:")
            for deployment in deployments:
                print(f"  {deployment['deployment_id']} - {deployment['status']} - {deployment.get('start_time', 'unknown')}")
        
        elif args.type == "backups":
            backups = manager.list_backups()
            print(f"\nFound {len(backups)} backups:")
            for backup in backups:
                size_mb = backup.size_bytes / (1024 * 1024) if backup.size_bytes > 0 else 0
                print(f"  {backup.backup_id} - {backup.backup_type} - {backup.timestamp} - {size_mb:.1f}MB")
    
    elif args.command == "rollback":
        if manager.rollback_to_deployment(args.deployment_id):
            print(f"Rollback to {args.deployment_id} completed successfully")
            return 0
        else:
            print(f"Rollback to {args.deployment_id} failed")
            return 1
    
    elif args.command == "restore":
        if manager.restore_from_backup(args.backup_id):
            print(f"Restore from {args.backup_id} completed successfully")
            return 0
        else:
            print(f"Restore from {args.backup_id} failed")
            return 1
    
    elif args.command == "backup":
        backup_id = manager.create_emergency_backup()
        if backup_id:
            print(f"Emergency backup created: {backup_id}")
            return 0
        else:
            print("Emergency backup failed")
            return 1
    
    elif args.command == "cleanup":
        manager.cleanup_old_backups(args.keep)
        print("Backup cleanup completed")
    
    return 0


if __name__ == "__main__":
    exit(main())