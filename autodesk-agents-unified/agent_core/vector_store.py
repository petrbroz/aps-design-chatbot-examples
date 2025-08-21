"""
OpenSearch vector store implementation for the AgentCore framework.
"""

import json
import uuid
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

from opensearchpy import OpenSearch, RequestsHttpConnection
from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore
from langchain_community.embeddings import BedrockEmbeddings

from .models import ToolResult
from .logging import get_logger


class OpenSearchVectorStore:
    """
    OpenSearch-based vector store implementation to replace FAISS.
    
    This class provides document indexing and similarity search capabilities
    using OpenSearch with Bedrock embeddings.
    """
    
    def __init__(
        self,
        opensearch_endpoint: str,
        index_name: str,
        embeddings_model_id: str = "amazon.titan-embed-text-v1",
        aws_region: str = "us-east-1",
        dimension: int = 1536,
        **opensearch_kwargs
    ):
        """
        Initialize the OpenSearch vector store.
        
        Args:
            opensearch_endpoint: OpenSearch cluster endpoint
            index_name: Name of the index to use
            embeddings_model_id: Bedrock embeddings model ID
            aws_region: AWS region for Bedrock
            dimension: Vector dimension (default 1536 for Titan)
            **opensearch_kwargs: Additional OpenSearch client parameters
        """
        self.opensearch_endpoint = opensearch_endpoint
        self.index_name = index_name
        self.dimension = dimension
        self.logger = get_logger(__name__)
        
        # Validate OpenSearch endpoint
        if not opensearch_endpoint or not opensearch_endpoint.strip():
            raise ValueError("OpenSearch endpoint is required and cannot be empty")
        
        # Initialize OpenSearch client
        self.client = OpenSearch(
            hosts=[opensearch_endpoint],
            connection_class=RequestsHttpConnection,
            use_ssl=True,
            verify_certs=True,
            **opensearch_kwargs
        )
        
        # Initialize Bedrock embeddings
        self.embeddings = BedrockEmbeddings(
            model_id=embeddings_model_id,
            region_name=aws_region
        )
        
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the vector store and create index if it doesn't exist."""
        if self._initialized:
            return
        
        try:
            # Check if index exists
            if not self.client.indices.exists(index=self.index_name):
                await self._create_index()
            
            self._initialized = True
            self.logger.info(
                f"OpenSearch vector store initialized",
                index_name=self.index_name,
                endpoint=self.opensearch_endpoint
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to initialize OpenSearch vector store",
                error=str(e),
                index_name=self.index_name
            )
            raise
    
    async def _create_index(self) -> None:
        """Create the OpenSearch index with proper mapping."""
        mapping = {
            "mappings": {
                "properties": {
                    "content": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "metadata": {
                        "type": "object",
                        "enabled": True
                    },
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": self.dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "l2",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 24
                            }
                        }
                    },
                    "timestamp": {
                        "type": "date"
                    }
                }
            },
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 100
                }
            }
        }
        
        self.client.indices.create(
            index=self.index_name,
            body=mapping
        )
        
        self.logger.info(
            f"Created OpenSearch index",
            index_name=self.index_name
        )
    
    async def add_documents(self, documents: List[Document]) -> List[str]:
        """
        Add documents to the OpenSearch index.
        
        Args:
            documents: List of documents to add
            
        Returns:
            List of document IDs that were added
        """
        if not self._initialized:
            await self.initialize()
        
        if not documents:
            return []
        
        document_ids = []
        
        try:
            # Prepare documents for bulk indexing
            bulk_body = []
            
            for doc in documents:
                doc_id = str(uuid.uuid4())
                document_ids.append(doc_id)
                
                # Generate embedding for the document content
                embedding = await self._generate_embedding(doc.page_content)
                
                # Prepare document for indexing
                doc_body = {
                    "content": doc.page_content,
                    "metadata": doc.metadata or {},
                    "embedding": embedding,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Add to bulk body
                bulk_body.append({
                    "index": {
                        "_index": self.index_name,
                        "_id": doc_id
                    }
                })
                bulk_body.append(doc_body)
            
            # Perform bulk indexing
            response = self.client.bulk(body=bulk_body)
            
            # Check for errors
            if response.get("errors"):
                failed_docs = [
                    item for item in response["items"] 
                    if "error" in item.get("index", {})
                ]
                if failed_docs:
                    self.logger.warning(
                        f"Some documents failed to index",
                        failed_count=len(failed_docs),
                        total_count=len(documents)
                    )
            
            self.logger.info(
                f"Added {len(documents)} documents to OpenSearch",
                index_name=self.index_name,
                document_count=len(documents)
            )
            
            return document_ids
            
        except Exception as e:
            self.logger.error(
                f"Failed to add documents to OpenSearch",
                error=str(e),
                document_count=len(documents)
            )
            raise
    
    async def similarity_search(
        self,
        query: str,
        k: int = 8,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        Perform similarity search using OpenSearch.
        
        Args:
            query: Search query text
            k: Number of results to return
            filter_dict: Optional metadata filters
            
        Returns:
            List of similar documents
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Generate embedding for the query
            query_embedding = await self._generate_embedding(query)
            
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
                "_source": ["content", "metadata", "timestamp"]
            }
            
            # Add metadata filters if provided
            if filter_dict:
                search_body["query"] = {
                    "bool": {
                        "must": [search_body["query"]],
                        "filter": [
                            {"term": {f"metadata.{key}": value}}
                            for key, value in filter_dict.items()
                        ]
                    }
                }
            
            # Perform search
            response = self.client.search(
                index=self.index_name,
                body=search_body
            )
            
            # Convert results to Document objects
            documents = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]
                doc = Document(
                    page_content=source["content"],
                    metadata={
                        **source.get("metadata", {}),
                        "_score": hit["_score"],
                        "_id": hit["_id"],
                        "timestamp": source.get("timestamp")
                    }
                )
                documents.append(doc)
            
            self.logger.debug(
                f"Similarity search completed",
                query_length=len(query),
                results_count=len(documents),
                k=k
            )
            
            return documents
            
        except Exception as e:
            self.logger.error(
                f"Similarity search failed",
                error=str(e),
                query_length=len(query),
                k=k
            )
            raise
    
    async def similarity_search_with_score(
        self,
        query: str,
        k: int = 8,
        filter_dict: Optional[Dict[str, Any]] = None
    ) -> List[Tuple[Document, float]]:
        """
        Perform similarity search and return documents with scores.
        
        Args:
            query: Search query text
            k: Number of results to return
            filter_dict: Optional metadata filters
            
        Returns:
            List of tuples containing (document, score)
        """
        documents = await self.similarity_search(query, k, filter_dict)
        return [(doc, doc.metadata.get("_score", 0.0)) for doc in documents]
    
    async def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for the given text using Bedrock.
        
        Args:
            text: Text to embed
            
        Returns:
            List of embedding values
        """
        try:
            # Use Bedrock embeddings to generate embedding
            embedding = await self.embeddings.aembed_query(text)
            return embedding
            
        except Exception as e:
            self.logger.error(
                f"Failed to generate embedding",
                error=str(e),
                text_length=len(text)
            )
            raise
    
    async def delete_documents(self, document_ids: List[str]) -> None:
        """
        Delete documents from the index.
        
        Args:
            document_ids: List of document IDs to delete
        """
        if not self._initialized:
            await self.initialize()
        
        if not document_ids:
            return
        
        try:
            # Prepare bulk delete body
            bulk_body = []
            for doc_id in document_ids:
                bulk_body.append({
                    "delete": {
                        "_index": self.index_name,
                        "_id": doc_id
                    }
                })
            
            # Perform bulk delete
            response = self.client.bulk(body=bulk_body)
            
            self.logger.info(
                f"Deleted {len(document_ids)} documents from OpenSearch",
                index_name=self.index_name,
                document_count=len(document_ids)
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to delete documents from OpenSearch",
                error=str(e),
                document_count=len(document_ids)
            )
            raise
    
    async def clear_index(self) -> None:
        """Clear all documents from the index."""
        if not self._initialized:
            await self.initialize()
        
        try:
            # Delete all documents
            self.client.delete_by_query(
                index=self.index_name,
                body={"query": {"match_all": {}}}
            )
            
            self.logger.info(
                f"Cleared all documents from index",
                index_name=self.index_name
            )
            
        except Exception as e:
            self.logger.error(
                f"Failed to clear index",
                error=str(e),
                index_name=self.index_name
            )
            raise
    
    async def get_document_count(self) -> int:
        """
        Get the total number of documents in the index.
        
        Returns:
            Number of documents in the index
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            response = self.client.count(index=self.index_name)
            return response["count"]
            
        except Exception as e:
            self.logger.error(
                f"Failed to get document count",
                error=str(e),
                index_name=self.index_name
            )
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the OpenSearch cluster.
        
        Returns:
            Health status information
        """
        try:
            cluster_health = self.client.cluster.health()
            index_exists = self.client.indices.exists(index=self.index_name)
            
            if index_exists:
                doc_count = await self.get_document_count()
            else:
                doc_count = 0
            
            return {
                "cluster_status": cluster_health.get("status"),
                "cluster_name": cluster_health.get("cluster_name"),
                "index_exists": index_exists,
                "document_count": doc_count,
                "initialized": self._initialized
            }
            
        except Exception as e:
            self.logger.error(
                f"Health check failed",
                error=str(e)
            )
            return {
                "cluster_status": "unknown",
                "error": str(e),
                "initialized": self._initialized
            }
    
    def as_retriever(self, search_kwargs: Optional[Dict[str, Any]] = None):
        """
        Create a retriever interface compatible with LangChain.
        
        Args:
            search_kwargs: Additional search parameters
            
        Returns:
            OpenSearchRetriever instance
        """
        return OpenSearchRetriever(
            vector_store=self,
            search_kwargs=search_kwargs or {}
        )


class OpenSearchRetriever:
    """
    LangChain-compatible retriever interface for OpenSearch vector store.
    """
    
    def __init__(self, vector_store: OpenSearchVectorStore, search_kwargs: Dict[str, Any]):
        self.vector_store = vector_store
        self.search_kwargs = search_kwargs
    
    async def get_relevant_documents(self, query: str) -> List[Document]:
        """
        Get relevant documents for the given query.
        
        Args:
            query: Search query
            
        Returns:
            List of relevant documents
        """
        k = self.search_kwargs.get("k", 8)
        filter_dict = self.search_kwargs.get("filter", None)
        
        return await self.vector_store.similarity_search(
            query=query,
            k=k,
            filter_dict=filter_dict
        )
    
    async def aget_relevant_documents(self, query: str) -> List[Document]:
        """Async version of get_relevant_documents."""
        return await self.get_relevant_documents(query)