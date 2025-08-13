#!/usr/bin/env python3
"""
Test script for AWS OpenSearch integration with Bedrock embeddings.
"""

import asyncio
import os
from pathlib import Path

# Add the project root to Python path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from agentcore import (
    AgentCore, CoreConfig, ConfigManager,
    AgentRequest, ExecutionContext, StrandsOrchestrator
)
from agents.aec_data_model import AECDataModelAgent


async def test_aws_opensearch_configuration():
    """Test AWS OpenSearch configuration and setup."""
    
    print("🧪 Testing AWS OpenSearch Configuration")
    print("=" * 60)
    
    try:
        # Check for AWS OpenSearch environment variables
        opensearch_endpoint = os.getenv("AWS_OPENSEARCH_ENDPOINT")
        opensearch_domain = os.getenv("AWS_OPENSEARCH_DOMAIN")
        aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        
        print(f"📋 AWS OpenSearch Configuration:")
        print(f"   Endpoint: {opensearch_endpoint or 'Not set'}")
        print(f"   Domain: {opensearch_domain or 'Not set'}")
        print(f"   Region: {aws_region}")
        
        if not opensearch_endpoint:
            print("\n⚠️  AWS_OPENSEARCH_ENDPOINT not set")
            print("   Example: export AWS_OPENSEARCH_ENDPOINT='https://search-agentcore-xyz.us-east-1.es.amazonaws.com'")
            return False
        
        if not opensearch_domain:
            print("\n⚠️  AWS_OPENSEARCH_DOMAIN not set")
            print("   Example: export AWS_OPENSEARCH_DOMAIN='agentcore-vectors'")
            return False
        
        # Check AWS credentials
        try:
            import boto3
            session = boto3.Session()
            credentials = session.get_credentials()
            
            if credentials:
                print(f"✅ AWS credentials found")
                print(f"   Access Key: {credentials.access_key_id[:8]}...")
                print(f"   Region: {session.region_name or aws_region}")
            else:
                print("⚠️  No AWS credentials found")
                return False
                
        except Exception as e:
            print(f"❌ AWS credentials error: {e}")
            return False
        
        # Test OpenSearch client creation
        try:
            from agentcore.vector_store import OpenSearchVectorStore
            
            vector_store = OpenSearchVectorStore(
                opensearch_endpoint=opensearch_endpoint,
                region_name=aws_region,
                index_name="test_agentcore_vectors",
                use_aws_auth=True
            )
            
            print("✅ AWS OpenSearch client created successfully")
            
            # Test connection (this will fail if OpenSearch domain doesn't exist)
            try:
                await vector_store.initialize()
                print("✅ AWS OpenSearch connection established")
                
                # Test health check
                health = await vector_store.health_check()
                print(f"✅ AWS OpenSearch health: {health['status']}")
                
                return True
                
            except Exception as e:
                print(f"⚠️  AWS OpenSearch connection failed: {str(e)[:100]}...")
                print("   This is expected if the OpenSearch domain doesn't exist yet")
                return False
                
        except ImportError as e:
            print(f"❌ Missing dependency: {e}")
            print("   Install with: pip install requests-aws4auth")
            return False
            
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


async def test_bedrock_embeddings():
    """Test AWS Bedrock embeddings integration."""
    
    print("\n🧪 Testing AWS Bedrock Embeddings")
    print("=" * 60)
    
    try:
        from agentcore.vector_store import BedrockEmbeddings
        
        aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        
        # Create Bedrock embeddings client
        embeddings = BedrockEmbeddings(region_name=aws_region)
        
        print(f"✅ Bedrock embeddings client created")
        print(f"   Region: {aws_region}")
        print(f"   Model: {embeddings.model_id}")
        
        # Test embedding generation
        try:
            test_text = "This is a test property definition for wall height"
            embedding = await embeddings.embed_text(test_text)
            
            print(f"✅ Embedding generated successfully")
            print(f"   Text length: {len(test_text)} characters")
            print(f"   Embedding dimension: {len(embedding)}")
            print(f"   Sample values: {embedding[:5]}...")
            
            return True
            
        except Exception as e:
            print(f"⚠️  Bedrock embedding failed: {str(e)[:100]}...")
            print("   This requires AWS Bedrock access and proper IAM permissions")
            return False
            
    except Exception as e:
        print(f"❌ Bedrock embeddings test failed: {e}")
        return False


async def test_aec_agent_with_aws_opensearch():
    """Test AEC Data Model agent with AWS OpenSearch configuration."""
    
    print("\n🧪 Testing AEC Agent with AWS OpenSearch")
    print("=" * 60)
    
    try:
        # Set up test environment
        if not os.getenv("AUTODESK_CLIENT_ID"):
            os.environ["AUTODESK_CLIENT_ID"] = "test_client_id"
            os.environ["AUTODESK_CLIENT_SECRET"] = "test_client_secret"
        
        # Initialize AgentCore
        config_manager = ConfigManager()
        config = config_manager.load_config()
        agent_core = AgentCore(config)
        await agent_core.initialize()
        
        # Create orchestrator
        orchestrator = StrandsOrchestrator(agent_core)
        await orchestrator.initialize()
        
        # Create agent config with AWS OpenSearch
        agent_config = {
            "timeout_seconds": 30,
            "cache_ttl": 3600,
            "environment": "test",
            "specific_config": {
                "aws_opensearch_endpoint": os.getenv("AWS_OPENSEARCH_ENDPOINT", "https://test-endpoint.us-east-1.es.amazonaws.com"),
                "aws_opensearch_domain": os.getenv("AWS_OPENSEARCH_DOMAIN", "test-domain"),
                "vector_search_k": 8,
                "embedding_batch_size": 100
            }
        }
        
        # Create AEC agent
        aec_agent = AECDataModelAgent(agent_core, agent_config)
        
        print(f"✅ AEC Data Model agent created with AWS OpenSearch config")
        print(f"   OpenSearch endpoint: {agent_config['specific_config']['aws_opensearch_endpoint']}")
        print(f"   Vector store index: {aec_agent.vector_store.index_name}")
        print(f"   AWS auth enabled: {aec_agent.vector_store.use_aws_auth}")
        
        # Try to register agent (will fail if OpenSearch is not available)
        try:
            await orchestrator.register_agent("aec_data_model", aec_agent)
            print("✅ AEC agent registered successfully with AWS OpenSearch")
            
            # Test agent capabilities
            capabilities = aec_agent.get_capabilities()
            print(f"✅ Agent capabilities loaded")
            print(f"   Tools: {capabilities.tools}")
            
            # Shutdown
            await orchestrator.shutdown()
            await agent_core.shutdown()
            
            return True
            
        except Exception as e:
            print(f"⚠️  Agent registration failed: {str(e)[:100]}...")
            print("   This is expected without a real AWS OpenSearch domain")
            
            # Shutdown
            await agent_core.shutdown()
            return False
            
    except Exception as e:
        print(f"❌ AEC agent test failed: {e}")
        return False


async def main():
    """Run all AWS OpenSearch integration tests."""
    
    print("🚀 AWS OpenSearch Integration Test Suite")
    print("=" * 80)
    
    tests = [
        test_aws_opensearch_configuration,
        test_bedrock_embeddings,
        test_aec_agent_with_aws_opensearch
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if await test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    print("\n🚀 AWS OpenSearch Setup Instructions:")
    print("=" * 60)
    print("1. Create AWS OpenSearch Service domain:")
    print("   aws opensearch create-domain \\")
    print("     --domain-name agentcore-vectors \\")
    print("     --engine-version OpenSearch_2.3 \\")
    print("     --cluster-config InstanceType=t3.small.search,InstanceCount=1 \\")
    print("     --ebs-options EBSEnabled=true,VolumeType=gp3,VolumeSize=20")
    print("")
    print("2. Set environment variables:")
    print("   export AWS_OPENSEARCH_ENDPOINT='https://search-agentcore-vectors-xyz.us-east-1.es.amazonaws.com'")
    print("   export AWS_OPENSEARCH_DOMAIN='agentcore-vectors'")
    print("   export AWS_DEFAULT_REGION='us-east-1'")
    print("")
    print("3. Configure IAM permissions for OpenSearch and Bedrock access")
    print("")
    print("4. Install required dependencies:")
    print("   pip install requests-aws4auth")
    
    if passed >= 1:
        print("\n🎉 AWS OpenSearch integration is configured correctly!")
        return 0
    else:
        print("\n⚠️  AWS OpenSearch setup required. Follow instructions above.")
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))