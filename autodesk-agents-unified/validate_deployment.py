#!/usr/bin/env python3
"""
Validation script for deployment configuration.
"""

import os
import sys
import yaml
from pathlib import Path

def validate_config_files():
    """Validate all configuration files."""
    config_dir = Path("config")
    config_files = ["config.yaml", "development.yaml", "production.yaml", "local.yaml"]
    
    print("🔍 Validating configuration files...")
    
    for config_file in config_files:
        config_path = config_dir / config_file
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config_data = yaml.safe_load(f)
                    
                # Basic validation
                if 'core' not in config_data:
                    print(f"❌ {config_file}: Missing 'core' section")
                    return False
                    
                if 'agents' not in config_data:
                    print(f"❌ {config_file}: Missing 'agents' section")
                    return False
                    
                print(f"✅ {config_file}: Valid")
                
            except yaml.YAMLError as e:
                print(f"❌ {config_file}: Invalid YAML - {e}")
                return False
        else:
            print(f"⚠️  {config_file}: Not found")
    
    return True

def validate_docker_files():
    """Validate Docker configuration files."""
    docker_files = [
        "Dockerfile",
        "docker-compose.yml", 
        "docker-compose.prod.yml",
        ".dockerignore",
        "nginx.conf"
    ]
    
    print("\n🐳 Validating Docker files...")
    
    for docker_file in docker_files:
        if Path(docker_file).exists():
            print(f"✅ {docker_file}: Found")
        else:
            print(f"❌ {docker_file}: Missing")
            return False
    
    return True

def validate_scripts():
    """Validate deployment scripts."""
    script_files = [
        "scripts/deploy.sh",
        "scripts/setup-dev.sh"
    ]
    
    print("\n📜 Validating scripts...")
    
    for script_file in script_files:
        script_path = Path(script_file)
        if script_path.exists():
            # Check if executable
            if os.access(script_path, os.X_OK):
                print(f"✅ {script_file}: Found and executable")
            else:
                print(f"⚠️  {script_file}: Found but not executable")
        else:
            print(f"❌ {script_file}: Missing")
            return False
    
    return True

def validate_config_manager():
    """Validate configuration manager functionality."""
    print("\n⚙️  Validating configuration manager...")
    
    try:
        # Import and test configuration manager
        sys.path.append('.')
        from agent_core.config import ConfigManager, CoreConfig
        
        # Test with development config
        config_manager = ConfigManager(
            config_path="config/development.yaml",
            enable_hot_reload=False
        )
        
        # Load configuration
        config = config_manager.load_config()
        print(f"✅ Configuration loaded: {config.aws_region}")
        
        # Validate configuration
        is_valid, error_msg = config_manager.validate_config()
        if is_valid:
            print("✅ Configuration validation passed")
        else:
            print(f"❌ Configuration validation failed: {error_msg}")
            return False
            
        # Test agent configuration
        agent_config = config_manager.get_agent_config("model_properties")
        print(f"✅ Agent config loaded: {len(agent_config.tools)} tools")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration manager test failed: {e}")
        return False

def main():
    """Main validation function."""
    print("🚀 Deployment Configuration Validation")
    print("=" * 50)
    
    # Change to the correct directory
    os.chdir("autodesk-agents-unified")
    
    all_valid = True
    
    # Run validations
    all_valid &= validate_config_files()
    all_valid &= validate_docker_files()
    all_valid &= validate_scripts()
    all_valid &= validate_config_manager()
    
    print("\n" + "=" * 50)
    if all_valid:
        print("🎉 All validations passed! Deployment configuration is ready.")
        return 0
    else:
        print("❌ Some validations failed. Please check the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())