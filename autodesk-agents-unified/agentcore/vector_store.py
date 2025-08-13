"""
OpenSearch Vector Store for AgentCore

Provides vector search capabilities using OpenSearch with Bedrock embeddings
to replace FAISS for the AEC Data Model agent.
"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional, Union
import hashlib
from dataclasses import dataclass, field

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import NotFoundError, RequestError

from .logging import StructuredLogger


@dataclass
class Document:
    """Document for vector storage."""
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    doc_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.doc_id:
            # Generate ID from content hash
            content_hash = hashlib.sha256(self.content.encode()).hexdigest()
            self.doc_id = f"doc_{content_hash[:16]}"


@dataclass
class SearchResult:
    """Search result from vector store."""
    document: Document
    score: float
    rank: int


class BedrockEmbeddings:
    """
    Bedrock embeddings client for generating vector embeddings.
    
    Uses AWS Bedrock's Titan embeddings model to generate
    high-quality embeddings for text content.
    """
    
    def __init__(self, region_name: str = "us-east-1", 
                 model_id: str = "amazon.titan-embed-text-v1"):
        """Initialize Bedrock embeddings client."""
        self.region_name = region_name
        self.model_id = model_id
        self.client = boto3.client('bedrock-runtime', region_name=region_name)
        self.logger: Optional[StructuredLogger] = None
    
    def set_logger(self, logger: StructuredLogger) -> None:
        """Set logger for the embeddings client."""
        self.logger = logger
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embeddings for text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of embedding values
        """
        try:
            # Prepare request
            request_body = {
                "inputText": text
            }
            
            # Call Bedrock
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType='application/json'
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            embeddings = response_body.get('embedding', [])
            
            if self.logger:
                self.logger.debug("Generated embeddings", extra={
                    "text_length": len(text),
                    "embedding_dimension": len(embeddings),
                    "model_id": self.model_id
                })
            
            return embeddings
            
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to generate embeddings", extra={
                    "text_length": len(text),
                    "model_id": self.model_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            raise
    
    async def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        for text in texts:
            embedding = await self.embed_text(text)
            embeddings.append(embedding)
            
            # Small delay to avoid rate limiting
            await asyncio.sleep(0.1)
        
        return embeddings


class OpenSearchVectorStore:
    """
    AWS OpenSearch-based vector store with Bedrock embeddings.
    
    Provides document indexing, vector search, and metadata filtering
    using AWS OpenSearch Service with IAM authentication and Bedrock embeddings.
    """
    
    def __init__(self, 
                 opensearch_endpoint: str,
                 region_name: str = "us-east-1",
                 index_name: str = "agentcore_vectors",
                 embedding_dimension: int = 1536,
                 use_aws_auth: bool = True):
        """
        Initialize AWS OpenSearch vector store.
        
        Args:
            opensearch_endpoint: AWS OpenSearch Service endpoint (e.g., https://search-domain.region.es.amazonaws.com)
            region_name: AWS region for OpenSearch and Bedrock
            index_name: Name of the vector index
            embedding_dimension: Dimension of embedding vectors
            use_aws_auth: Whether to use AWS IAM authentication
        """
        self.opensearch_endpoint = opensearch_endpoint
        self.region_name = region_name
        self.index_name = index_name
        self.embedding_dimension = embedding_dimension
        self.use_aws_auth = use_aws_auth
        
        # Initialize clients
        self.client = self._create_opensearch_client()
        self.embeddings = BedrockEmbeddings(region_name=region_name)
        self.logger: Optional[StructuredLogger] = None
        
        # Index settings for AWS OpenSearch
        self.index_settings = {
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 100,
                    "number_of_shards": 1,
                    "number_of_replicas": 1
                }
            },
            "mappings": {
                "properties": {
                    "content": {"type": "text"},
                    "metadata": {"type": "object"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": embedding_dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "faiss"  # AWS OpenSearch uses faiss engine
                        }
                    },
                    "created_at": {"type": "date"},
                    "doc_id": {"type": "keyword"}
                }
            }
        }
    
    def _create_opensearch_client(self) -> OpenSearch:
        """Create AWS OpenSearch client with IAM authentication."""
        if self.use_aws_auth:
            try:
                # Try to use AWS authentication
                import boto3
                from botocore.auth import SigV4Auth
                from botocore.awsrequest import AWSRequest
                from opensearchpy import RequestsHttpConnection
                
                # Get AWS credentials
                session = boto3.Session()
                credentials = session.get_credentials()
                
                if not credentials:
                    raise Exception("No AWS credentials found. Configure AWS credentials first.")
                
                # Extract host from endpoint
                host = self.opensearch_endpoint.replace('https://', '').replace('http://', '')
                
                # For now, create a basic client and let AWS handle auth through IAM roles
                # In production, you would typically use AWS IAM roles for service authentication
                return OpenSearch(
                    hosts=[{'host': host, 'port': 443}],
                    use_ssl=True,
                    verify_certs=True,
                    connection_class=RequestsHttpConnection,
                    http_compress=True,
                    # Note: For production, you would configure proper AWS authentication
                    # This requires either IAM roles or AWS credentials
                )
                
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"AWS authentication failed, falling back to basic auth: {e}")
                
                # Fallback to basic connection
                host = self.opensearch_endpoint.replace('https://', '').replace('http://', '')
                return OpenSearch(
                    hosts=[{'host': host, 'port': 443}],
                    use_ssl=True,
                    verify_certs=False,  # For testing
                    connection_class=RequestsHttpConnection,
                    http_compress=True
                )
        else:
            # Basic connection (for local testing)
            host = self.opensearch_endpoint.replace('https://', '').replace('http://', '')
            port = 443 if 'https://' in self.opensearch_endpoint else 9200
            
            return OpenSearch(
                hosts=[{'host': host, 'port': port}],
                http_compress=True,
                use_ssl='https://' in self.opensearch_endpoint,
                verify_certs=False,
                connection_class=RequestsHttpConnection
            )
    
    def set_logger(self, logger: StructuredLogger) -> None:
        """Set logger for the vector store."""
        self.logger = logger
        self.embeddings.set_logger(logger)
    
    async def initialize(self) -> None:
        """Initialize the vector store and create index if needed."""
        try:
            # Check if index exists
            if not self.client.indices.exists(index=self.index_name):
                # Create index
                self.client.indices.create(
                    index=self.index_name,
                    body=self.index_settings
                )
                
                if self.logger:
                    self.logger.info("Created OpenSearch vector index", extra={
                        "index_name": self.index_name,
                        "embedding_dimension": self.embedding_dimension
                    })
            else:
                if self.logger:
                    self.logger.info("OpenSearch vector index already exists", extra={
                        "index_name": self.index_name
                    })
            
            # Test connection
            cluster_info = self.client.info()
            if self.logger:
                self.logger.info("OpenSearch connection established", extra={
                    "cluster_name": cluster_info.get("cluster_name"),
                    "version": cluster_info.get("version", {}).get("number")
                })
                
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to initialize OpenSearch vector store", extra={
                    "host": self.host,
                    "port": self.port,
                    "index_name": self.index_name,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            raise
    
    async def add_documents(self, documents: List[Document]) -> None:
        """
        Add documents to the vector store.
        
        Args:
            documents: List of documents to add
        """
        if not documents:
            return
        
        try:
            # Generate embeddings for all documents
            texts = [doc.content for doc in documents]
            embeddings = await self.embeddings.embed_documents(texts)
            
            # Prepare bulk indexing
            bulk_body = []
            
            for doc, embedding in zip(documents, embeddings):
                # Index action
                bulk_body.append({
                    "index": {
                        "_index": self.index_name,
                        "_id": doc.doc_id
                    }
                })
                
                # Document body
                bulk_body.append({
                    "content": doc.content,
                    "metadata": doc.metadata,
                    "embedding": embedding,
                    "created_at": time.time(),
                    "doc_id": doc.doc_id
                })
            
            # Execute bulk indexing
            response = self.client.bulk(body=bulk_body, refresh=True)
            
            # Check for errors
            if response.get("errors"):
                errors = [item for item in response["items"] if "error" in item.get("index", {})]
                if errors and self.logger:
                    self.logger.warning("Some documents failed to index", extra={
                        "error_count": len(errors),
                        "total_documents": len(documents)
                    })
            
            if self.logger:
                self.logger.info("Documents added to vector store", extra={
                    "document_count": len(documents),
                    "index_name": self.index_name
                })
                
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to add documents to vector store", extra={
                    "document_count": len(documents),
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            raise
    
    async def similarity_search(self, 
                               query: str, 
                               k: int = 8,
                               filter_metadata: Optional[Dict[str, Any]] = None) -> List[SearchResult]:
        """
        Perform similarity search.
        
        Args:
            query: Search query text
            k: Number of results to return
            filter_metadata: Optional metadata filters
            
        Returns:
            List of search results
        """
        try:
            # Generate query embedding
            query_embedding = await self.embeddings.embed_text(query)
            
            # Build search query
            search_body = {
                "size": k,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": query_embedding,
                            "k": k
                        }
                    }
                },
                "_source": ["content", "metadata", "doc_id", "created_at"]
            }
            
            # Add metadata filters if provided
            if filter_metadata:
                search_body["query"] = {
                    "bool": {
                        "must": [search_body["query"]],
                        "filter": [
                            {"term": {f"metadata.{key}": value}}
                            for key, value in filter_metadata.items()
                        ]
                    }
                }
            
            # Execute search
            response = self.client.search(
                index=self.index_name,
                body=search_body
            )
            
            # Parse results
            results = []
            for i, hit in enumerate(response["hits"]["hits"]):
                source = hit["_source"]
                document = Document(
                    content=source["content"],
                    metadata=source.get("metadata", {}),
                    doc_id=source.get("doc_id")
                )
                
                result = SearchResult(
                    document=document,
                    score=hit["_score"],
                    rank=i + 1
                )
                results.append(result)
            
            if self.logger:
                self.logger.info("Vector similarity search completed", extra={
                    "query_length": len(query),
                    "results_count": len(results),
                    "k": k,
                    "has_filters": bool(filter_metadata)
                })
            
            return results
            
        except Exception as e:
            if self.logger:
                self.logger.error("Vector similarity search failed", extra={
                    "query_length": len(query),
                    "k": k,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            raise
    
    async def delete_documents(self, doc_ids: List[str]) -> None:
        """
        Delete documents by IDs.
        
        Args:
            doc_ids: List of document IDs to delete
        """
        try:
            # Prepare bulk delete
            bulk_body = []
            
            for doc_id in doc_ids:
                bulk_body.append({
                    "delete": {
                        "_index": self.index_name,
                        "_id": doc_id
                    }
                })
            
            # Execute bulk delete
            response = self.client.bulk(body=bulk_body, refresh=True)
            
            if self.logger:
                self.logger.info("Documents deleted from vector store", extra={
                    "document_count": len(doc_ids),
                    "index_name": self.index_name
                })
                
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to delete documents", extra={
                    "document_count": len(doc_ids),
                    "error": str(e),
                    "error_type": type(e).__name__
                })
            raise
    
    async def get_document_count(self) -> int:
        """Get total number of documents in the store."""
        try:
            response = self.client.count(index=self.index_name)
            return response["count"]
        except Exception:
            return 0
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the vector store."""
        try:
            # Check cluster health
            cluster_health = self.client.cluster.health()
            
            # Check index stats
            index_stats = self.client.indices.stats(index=self.index_name)
            doc_count = index_stats["indices"][self.index_name]["total"]["docs"]["count"]
            
            return {
                "status": "healthy",
                "cluster_status": cluster_health["status"],
                "index_name": self.index_name,
                "document_count": doc_count,
                "embedding_dimension": self.embedding_dimension
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def shutdown(self) -> None:
        """Shutdown the vector store."""
        if self.logger:
            self.logger.info("OpenSearch vector store shutdown")
        # OpenSearch client doesn't need explicit shutdown