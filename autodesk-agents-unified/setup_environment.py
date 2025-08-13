#!/usr/bin/env python3
"""
Environment Setup Script for AgentCore System

This script helps set up the necessary environment for running the AgentCore system.
"""

import os
import sys
import subprocess
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def check_aws_credentials():
    """Check if AWS credentials are configured"""
    logger.info("🔍 Checking AWS credentials...")
    
    # Check environment variables
    aws_key = os.getenv('AWS_ACCESS_KEY_ID')
    aws_secret = os.getenv('AWS_SECRET_ACCESS_KEY')
    
    if aws_key and aws_secret:
        logger.info("✅ AWS credentials found in environment variables")
        return True
    
    # Check AWS credentials file
    aws_creds_file = Path.home() / '.aws' / 'credentials'
    if aws_creds_file.exists():
        logger.info("✅ AWS credentials file found")
        return True
    
    logger.warning("⚠️  AWS credentials not found")
    logger.info("   You can set them up by:")
    logger.info("   1. Setting environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY")
    logger.info("   2. Running: aws configure")
    logger.info("   3. Using IAM roles (if running on AWS)")
    
    return False


def check_bedrock_access():
    """Check if AWS Bedrock is accessible"""
    logger.info("🔍 Checking AWS Bedrock access...")
    
    try:
        import boto3
        
        # Try to create a Bedrock client
        bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
        
        # Try to list available models (this will fail if no access)
        try:
            # This is a simple check - we don't actually need to call the API
            logger.info("✅ AWS Bedrock client created successfully")
            logger.info("   Note: Actual API access will be tested when making requests")
            return True
        except Exception as e:
            logger.warning(f"⚠️  AWS Bedrock access check failed: {e}")
            logger.info("   This might be due to permissions or region settings")
            return False
            
    except ImportError:
        logger.error("❌ boto3 not installed. Run: pip install boto3")
        return False


def check_opensearch():
    """Check if OpenSearch is available"""
    logger.info("🔍 Checking OpenSearch availability...")
    
    try:
        import requests
        
        # Try to connect to local OpenSearch
        response = requests.get('http://localhost:9200', timeout=5)
        
        if response.status_code == 200:
            logger.info("✅ OpenSearch is running locally")
            return True
        else:
            logger.warning("⚠️  OpenSearch responded with non-200 status")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.warning("⚠️  OpenSearch not running locally")
        logger.info("   You can:")
        logger.info("   1. Start OpenSearch locally: docker run -p 9200:9200 opensearchproject/opensearch:latest")
        logger.info("   2. Use a remote OpenSearch cluster")
        logger.info("   3. Skip vector search features for now")
        return False
    except Exception as e:
        logger.error(f"❌ Error checking OpenSearch: {e}")
        return False


def create_directories():
    """Create necessary directories"""
    logger.info("📁 Creating necessary directories...")
    
    directories = [
        'dev_cache',
        'logs',
        'test_results'
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        logger.info(f"   Created: {directory}/")
    
    logger.info("✅ Directories created")
    return True


def check_dependencies():
    """Check if all Python dependencies are installed"""
    logger.info("🔍 Checking Python dependencies...")
    
    required_packages = [
        'fastapi',
        'uvicorn',
        'boto3',
        'langchain',
        'langchain-aws',
        'opensearch-py',
        'pydantic',
        'pyyaml'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            # Handle special cases for package imports
            if package == 'opensearch-py':
                __import__('opensearchpy')
            elif package == 'langchain-aws':
                __import__('langchain_aws')
            elif package == 'pyyaml':
                __import__('yaml')
            else:
                __import__(package.replace('-', '_'))
            logger.info(f"   ✅ {package}")
        except ImportError:
            logger.error(f"   ❌ {package}")
            missing_packages.append(package)
    
    if missing_packages:
        logger.error("❌ Missing required packages")
        logger.info("   Install them with: pip install " + " ".join(missing_packages))
        return False
    
    logger.info("✅ All dependencies are installed")
    return True


def create_env_file():
    """Create .env file from example if it doesn't exist"""
    logger.info("🔧 Setting up environment file...")
    
    env_file = Path('.env')
    env_example = Path('.env.example')
    
    if env_file.exists():
        logger.info("✅ .env file already exists")
        return True
    
    if env_example.exists():
        # Copy example to .env
        with open(env_example, 'r') as src, open(env_file, 'w') as dst:
            dst.write(src.read())
        
        logger.info("✅ Created .env file from .env.example")
        logger.warning("⚠️  Please edit .env file with your actual credentials")
        return True
    
    logger.error("❌ .env.example file not found")
    return False


def main():
    """Main setup function"""
    logger.info("🚀 Setting up AgentCore Environment")
    logger.info("=" * 50)
    
    # Change to the correct directory
    os.chdir(Path(__file__).parent)
    
    checks = [
        ("Dependencies", check_dependencies),
        ("Directories", create_directories),
        ("Environment File", create_env_file),
        ("AWS Credentials", check_aws_credentials),
        ("AWS Bedrock", check_bedrock_access),
        ("OpenSearch", check_opensearch)
    ]
    
    results = {}
    
    for check_name, check_func in checks:
        try:
            if callable(check_func):
                results[check_name] = check_func()
            else:
                results[check_name] = check_func
        except Exception as e:
            logger.error(f"❌ Error in {check_name}: {e}")
            results[check_name] = False
        
        # Ensure all results are boolean
        if results[check_name] is None:
            results[check_name] = False
    
    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 SETUP SUMMARY")
    logger.info("=" * 50)
    
    for check_name, result in results.items():
        status = "✅ READY" if result else "❌ NEEDS ATTENTION"
        logger.info(f"{check_name:20} | {status}")
    
    passed = sum(results.values())
    total = len(results)
    
    logger.info(f"\nOverall: {passed}/{total} checks passed")
    
    if passed >= total - 1:  # Allow one failure (likely OpenSearch)
        logger.info("🎉 Environment is ready for AgentCore!")
        logger.info("\nNext steps:")
        logger.info("1. Edit .env file with your credentials")
        logger.info("2. Run: python server.py --config config/local_dev.yaml")
        return True
    else:
        logger.error("💥 Environment needs more setup")
        logger.info("\nPlease address the failed checks above")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)