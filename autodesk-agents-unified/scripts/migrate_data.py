#!/usr/bin/env python3
"""
Data migration script for Autodesk Agents Unified
Migrates cache data from standalone agent implementations to unified architecture
"""

import os
import json
import shutil
import logging
import argparse
import base64
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CacheMigrator:
    """Handles migration of cache data from standalone agents to unified architecture"""
    
    def __init__(self, source_dirs: List[str], target_dir: str, dry_run: bool = False):
        self.source_dirs = source_dirs
        self.target_dir = Path(target_dir)
        self.dry_run = dry_run
        self.migration_log = []
        
        # Create target directory structure
        if not dry_run:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            (self.target_dir / "model_properties").mkdir(exist_ok=True)
            (self.target_dir / "aec_data_model").mkdir(exist_ok=True)
            (self.target_dir / "model_derivatives").mkdir(exist_ok=True)
    
    def decode_cache_key(self, encoded_key: str) -> Optional[str]:
        """Decode base64 encoded cache keys to extract URN information"""
        try:
            decoded = base64.b64decode(encoded_key).decode('utf-8')
            return decoded
        except Exception as e:
            logger.warning(f"Failed to decode cache key {encoded_key}: {e}")
            return None
    
    def migrate_model_properties_cache(self, source_dir: str) -> int:
        """Migrate Model Properties agent cache data"""
        logger.info(f"Migrating Model Properties cache from {source_dir}")
        
        source_path = Path(source_dir) / "__cache__"
        if not source_path.exists():
            logger.warning(f"Source cache directory not found: {source_path}")
            return 0
        
        migrated_count = 0
        target_path = self.target_dir / "model_properties"
        
        for cache_dir in source_path.iterdir():
            if not cache_dir.is_dir():
                continue
                
            # Decode the cache key to get URN
            urn = self.decode_cache_key(cache_dir.name)
            if not urn:
                continue
            
            # Create sanitized directory name
            sanitized_name = cache_dir.name
            target_cache_dir = target_path / sanitized_name
            
            if not self.dry_run:
                target_cache_dir.mkdir(exist_ok=True)
            
            # Migrate cache files
            for cache_file in cache_dir.iterdir():
                if cache_file.is_file():
                    target_file = target_cache_dir / cache_file.name
                    
                    if not self.dry_run:
                        shutil.copy2(cache_file, target_file)
                    
                    self.migration_log.append({
                        "type": "model_properties",
                        "source": str(cache_file),
                        "target": str(target_file),
                        "urn": urn,
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    migrated_count += 1
        
        logger.info(f"Migrated {migrated_count} Model Properties cache files")
        return migrated_count
    
    def migrate_aec_data_model_cache(self, source_dir: str) -> int:
        """Migrate AEC Data Model agent cache data (FAISS to OpenSearch preparation)"""
        logger.info(f"Preparing AEC Data Model cache migration from {source_dir}")
        
        # Note: AEC Data Model uses FAISS which will be replaced by OpenSearch
        # This migration prepares the data structure but actual vector migration
        # will happen during first run of the new system
        
        source_path = Path(source_dir)
        migrated_count = 0
        target_path = self.target_dir / "aec_data_model"
        
        # Look for any cached property definitions or embeddings
        cache_files = [
            "property_definitions.json",
            "embeddings_cache.json",
            "faiss_index.bin",
            "vector_metadata.json"
        ]
        
        for cache_file in cache_files:
            source_file = source_path / cache_file
            if source_file.exists():
                target_file = target_path / cache_file
                
                if not self.dry_run:
                    shutil.copy2(source_file, target_file)
                
                self.migration_log.append({
                    "type": "aec_data_model",
                    "source": str(source_file),
                    "target": str(target_file),
                    "note": "Will be migrated to OpenSearch on first run",
                    "timestamp": datetime.now().isoformat()
                })
                
                migrated_count += 1
        
        logger.info(f"Prepared {migrated_count} AEC Data Model cache files for migration")
        return migrated_count
    
    def migrate_model_derivatives_cache(self, source_dir: str) -> int:
        """Migrate Model Derivatives agent cache data (SQLite databases)"""
        logger.info(f"Migrating Model Derivatives cache from {source_dir}")
        
        source_path = Path(source_dir)
        migrated_count = 0
        target_path = self.target_dir / "model_derivatives"
        
        # Look for SQLite database files
        for db_file in source_path.glob("*.db"):
            target_file = target_path / db_file.name
            
            if not self.dry_run:
                shutil.copy2(db_file, target_file)
            
            self.migration_log.append({
                "type": "model_derivatives",
                "source": str(db_file),
                "target": str(target_file),
                "timestamp": datetime.now().isoformat()
            })
            
            migrated_count += 1
        
        # Also look for any cached property databases
        for cache_dir in source_path.iterdir():
            if cache_dir.is_dir() and cache_dir.name.startswith("cache_"):
                for db_file in cache_dir.glob("*.db"):
                    target_subdir = target_path / cache_dir.name
                    if not self.dry_run:
                        target_subdir.mkdir(exist_ok=True)
                    
                    target_file = target_subdir / db_file.name
                    
                    if not self.dry_run:
                        shutil.copy2(db_file, target_file)
                    
                    self.migration_log.append({
                        "type": "model_derivatives",
                        "source": str(db_file),
                        "target": str(target_file),
                        "timestamp": datetime.now().isoformat()
                    })
                    
                    migrated_count += 1
        
        logger.info(f"Migrated {migrated_count} Model Derivatives cache files")
        return migrated_count
    
    def create_migration_manifest(self) -> None:
        """Create a manifest file documenting the migration"""
        manifest = {
            "migration_timestamp": datetime.now().isoformat(),
            "source_directories": self.source_dirs,
            "target_directory": str(self.target_dir),
            "total_files_migrated": len(self.migration_log),
            "migration_log": self.migration_log,
            "dry_run": self.dry_run
        }
        
        manifest_file = self.target_dir / "migration_manifest.json"
        
        if not self.dry_run:
            with open(manifest_file, 'w') as f:
                json.dump(manifest, f, indent=2)
        
        logger.info(f"Migration manifest {'would be' if self.dry_run else ''} created at {manifest_file}")
    
    def run_migration(self) -> Dict[str, int]:
        """Run the complete migration process"""
        logger.info("Starting cache data migration...")
        
        results = {
            "model_properties": 0,
            "aec_data_model": 0,
            "model_derivatives": 0
        }
        
        # Migrate each agent type
        for source_dir in self.source_dirs:
            source_path = Path(source_dir)
            
            if "acc-model-props-assistant" in str(source_path):
                results["model_properties"] += self.migrate_model_properties_cache(source_dir)
            elif "aec-data-model-assistant" in str(source_path):
                results["aec_data_model"] += self.migrate_aec_data_model_cache(source_dir)
            elif "aps-model-derivs-assistant" in str(source_path):
                results["model_derivatives"] += self.migrate_model_derivatives_cache(source_dir)
        
        # Create migration manifest
        self.create_migration_manifest()
        
        total_migrated = sum(results.values())
        logger.info(f"Migration completed. Total files migrated: {total_migrated}")
        
        return results


def main():
    parser = argparse.ArgumentParser(description="Migrate cache data to unified agent architecture")
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        required=True,
        help="Source directories containing agent cache data"
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        help="Target directory for unified cache"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually copying files"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate source directories
    for source_dir in args.source_dirs:
        if not Path(source_dir).exists():
            logger.error(f"Source directory does not exist: {source_dir}")
            return 1
    
    # Run migration
    migrator = CacheMigrator(args.source_dirs, args.target_dir, args.dry_run)
    results = migrator.run_migration()
    
    # Print summary
    print("\nMigration Summary:")
    print(f"Model Properties: {results['model_properties']} files")
    print(f"AEC Data Model: {results['aec_data_model']} files")
    print(f"Model Derivatives: {results['model_derivatives']} files")
    print(f"Total: {sum(results.values())} files")
    
    if args.dry_run:
        print("\nThis was a dry run. No files were actually migrated.")
    
    return 0


if __name__ == "__main__":
    exit(main())