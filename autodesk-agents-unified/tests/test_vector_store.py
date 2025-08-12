"""
Unit tests for OpenSearch vector store implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from langchain_core.documents import Document

from agent_core.vector_store import OpenSearchVectorStore, OpenSearchRetriever


@pytest.fixture
def mock_opensearch_client():
    """Mock OpenSearch client."""
    client = Mock()
    client.indices.exists.return_value = True
    client.indices.create.return_value = {"acknowledged": True}
    client.bulk.return_value = {"errors": False, "items": []}
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "doc1",
                    "_score": 0.95,
                    "_source": {
                        "content": "Test document content",
                        "metadata": {"id": "prop1", "name": "Test Property"},
                        "timestamp": "2024-01-01T00:00:00"
                    }
                }
            ]
        }
    }
    client.count.return_value = {"count": 1}
    client.cluster.health.return_value = {
        "status": "green",
        "cluster_name": "test-cluster"
    }
    client.delete_by_query.return_value = {"deleted": 1}
    return client


@pytest.fixture
def mock_bedrock_embeddings():
    """Mock Bedrock embeddings."""
    embeddings = Mock()
    embeddings.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3] * 512)  # 1536 dimensions
    return embeddings


@pytest.fixture
def vector_store(mock_opensearch_client, mock_bedrock_embeddings):
    """Create OpenSearch vector store with mocked dependencies."""
    with patch('agent_core.vector_store.OpenSearch', return_value=mock_opensearch_client), \
         patch('agent_core.vector_store.BedrockEmbeddings', return_value=mock_bedrock_embeddings):
        
        store = OpenSearchVectorStore(
            opensearch_endpoint="https://test-opensearch.com",
            index_name="test-index",
            embeddings_model_id="amazon.titan-embed-text-v1",
            aws_region="us-east-1"
        )
        return store


class TestOpenSearchVectorStore:
    """Test cases for OpenSearchVectorStore."""
    
    @pytest.mark.asyncio
    async def test_initialization(self, vector_store, mock_opensearch_client):
        """Test vector store initialization."""
        await vector_store.initialize()
        
        assert vector_store._initialized is True
        mock_opensearch_client.indices.exists.assert_called_once_with(index="test-index")
    
    @pytest.mark.asyncio
    async def test_create_index_when_not_exists(self, mock_opensearch_client, mock_bedrock_embeddings):
        """Test index creation when it doesn't exist."""
        mock_opensearch_client.indices.exists.return_value = False
        
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_opensearch_client), \
             patch('agent_core.vector_store.BedrockEmbeddings', return_value=mock_bedrock_embeddings):
            
            store = OpenSearchVectorStore(
                opensearch_endpoint="https://test-opensearch.com",
                index_name="test-index"
            )
            
            await store.initialize()
            
            mock_opensearch_client.indices.create.assert_called_once()
            create_call_args = mock_opensearch_client.indices.create.call_args
            assert create_call_args[1]["index"] == "test-index"
            assert "mappings" in create_call_args[1]["body"]
    
    @pytest.mark.asyncio
    async def test_add_documents(self, vector_store, mock_opensearch_client, mock_bedrock_embeddings):
        """Test adding documents to the index."""
        await vector_store.initialize()
        
        documents = [
            Document(
                page_content="Test property 1",
                metadata={"id": "prop1", "name": "Property 1"}
            ),
            Document(
                page_content="Test property 2",
                metadata={"id": "prop2", "name": "Property 2"}
            )
        ]
        
        document_ids = await vector_store.add_documents(documents)
        
        assert len(document_ids) == 2
        assert all(isinstance(doc_id, str) for doc_id in document_ids)
        
        # Verify bulk indexing was called
        mock_opensearch_client.bulk.assert_called_once()
        bulk_call_args = mock_opensearch_client.bulk.call_args[1]["body"]
        
        # Should have 4 items (2 index operations + 2 documents)
        assert len(bulk_call_args) == 4
        
        # Verify embeddings were generated for each document
        assert mock_bedrock_embeddings.aembed_query.call_count == 2
    
    @pytest.mark.asyncio
    async def test_similarity_search(self, vector_store, mock_opensearch_client, mock_bedrock_embeddings):
        """Test similarity search functionality."""
        await vector_store.initialize()
        
        results = await vector_store.similarity_search("test query", k=5)
        
        assert len(results) == 1
        assert isinstance(results[0], Document)
        assert results[0].page_content == "Test document content"
        assert results[0].metadata["id"] == "prop1"
        assert results[0].metadata["_score"] == 0.95
        
        # Verify search was called with correct parameters
        mock_opensearch_client.search.assert_called_once()
        search_call_args = mock_opensearch_client.search.call_args[1]
        assert search_call_args["index"] == "test-index"
        assert search_call_args["body"]["size"] == 5
        
        # Verify embedding was generated for query
        mock_bedrock_embeddings.aembed_query.assert_called_with("test query")
    
    @pytest.mark.asyncio
    async def test_similarity_search_with_filter(self, vector_store, mock_opensearch_client):
        """Test similarity search with metadata filters."""
        await vector_store.initialize()
        
        filter_dict = {"category": "structural"}
        await vector_store.similarity_search("test query", k=3, filter_dict=filter_dict)
        
        # Verify search was called with filter
        search_call_args = mock_opensearch_client.search.call_args[1]
        query = search_call_args["body"]["query"]
        
        assert "bool" in query
        assert "filter" in query["bool"]
        assert query["bool"]["filter"][0]["term"]["metadata.category"] == "structural"
    
    @pytest.mark.asyncio
    async def test_similarity_search_with_score(self, vector_store):
        """Test similarity search with scores."""
        await vector_store.initialize()
        
        results = await vector_store.similarity_search_with_score("test query", k=3)
        
        assert len(results) == 1
        document, score = results[0]
        assert isinstance(document, Document)
        assert score == 0.95
    
    @pytest.mark.asyncio
    async def test_delete_documents(self, vector_store, mock_opensearch_client):
        """Test document deletion."""
        await vector_store.initialize()
        
        document_ids = ["doc1", "doc2", "doc3"]
        await vector_store.delete_documents(document_ids)
        
        # Verify bulk delete was called
        mock_opensearch_client.bulk.assert_called_once()
        bulk_call_args = mock_opensearch_client.bulk.call_args[1]["body"]
        
        # Should have 3 delete operations
        assert len(bulk_call_args) == 3
        for i, operation in enumerate(bulk_call_args):
            assert "delete" in operation
            assert operation["delete"]["_id"] == document_ids[i]
    
    @pytest.mark.asyncio
    async def test_clear_index(self, vector_store, mock_opensearch_client):
        """Test clearing all documents from index."""
        await vector_store.initialize()
        
        await vector_store.clear_index()
        
        mock_opensearch_client.delete_by_query.assert_called_once_with(
            index="test-index",
            body={"query": {"match_all": {}}}
        )
    
    @pytest.mark.asyncio
    async def test_get_document_count(self, vector_store, mock_opensearch_client):
        """Test getting document count."""
        await vector_store.initialize()
        
        count = await vector_store.get_document_count()
        
        assert count == 1
        mock_opensearch_client.count.assert_called_once_with(index="test-index")
    
    @pytest.mark.asyncio
    async def test_health_check(self, vector_store, mock_opensearch_client):
        """Test health check functionality."""
        await vector_store.initialize()
        
        health = await vector_store.health_check()
        
        assert health["cluster_status"] == "green"
        assert health["cluster_name"] == "test-cluster"
        assert health["index_exists"] is True
        assert health["document_count"] == 1
        assert health["initialized"] is True
    
    @pytest.mark.asyncio
    async def test_health_check_with_error(self, vector_store, mock_opensearch_client):
        """Test health check when there's an error."""
        await vector_store.initialize()
        
        mock_opensearch_client.cluster.health.side_effect = Exception("Connection failed")
        
        health = await vector_store.health_check()
        
        assert health["cluster_status"] == "unknown"
        assert "error" in health
        assert health["initialized"] is True
    
    @pytest.mark.asyncio
    async def test_embedding_generation_error(self, vector_store, mock_bedrock_embeddings):
        """Test handling of embedding generation errors."""
        await vector_store.initialize()
        
        mock_bedrock_embeddings.aembed_query.side_effect = Exception("Embedding failed")
        
        with pytest.raises(Exception, match="Embedding failed"):
            await vector_store.similarity_search("test query")
    
    @pytest.mark.asyncio
    async def test_opensearch_connection_error(self, mock_bedrock_embeddings):
        """Test handling of OpenSearch connection errors."""
        mock_client = Mock()
        mock_client.indices.exists.side_effect = Exception("Connection failed")
        
        with patch('agent_core.vector_store.OpenSearch', return_value=mock_client), \
             patch('agent_core.vector_store.BedrockEmbeddings', return_value=mock_bedrock_embeddings):
            
            store = OpenSearchVectorStore(
                opensearch_endpoint="https://test-opensearch.com",
                index_name="test-index"
            )
            
            with pytest.raises(Exception, match="Connection failed"):
                await store.initialize()
    
    def test_as_retriever(self, vector_store):
        """Test creating a retriever interface."""
        search_kwargs = {"k": 10, "filter": {"category": "test"}}
        retriever = vector_store.as_retriever(search_kwargs=search_kwargs)
        
        assert isinstance(retriever, OpenSearchRetriever)
        assert retriever.vector_store == vector_store
        assert retriever.search_kwargs == search_kwargs


class TestOpenSearchRetriever:
    """Test cases for OpenSearchRetriever."""
    
    @pytest.fixture
    def mock_vector_store(self):
        """Mock vector store for retriever tests."""
        store = Mock()
        store.similarity_search = AsyncMock(return_value=[
            Document(page_content="Test doc", metadata={"id": "1"})
        ])
        return store
    
    @pytest.mark.asyncio
    async def test_get_relevant_documents(self, mock_vector_store):
        """Test getting relevant documents."""
        retriever = OpenSearchRetriever(
            vector_store=mock_vector_store,
            search_kwargs={"k": 5, "filter": {"category": "test"}}
        )
        
        results = await retriever.get_relevant_documents("test query")
        
        assert len(results) == 1
        mock_vector_store.similarity_search.assert_called_once_with(
            query="test query",
            k=5,
            filter_dict={"category": "test"}
        )
    
    @pytest.mark.asyncio
    async def test_aget_relevant_documents(self, mock_vector_store):
        """Test async version of get_relevant_documents."""
        retriever = OpenSearchRetriever(
            vector_store=mock_vector_store,
            search_kwargs={"k": 3}
        )
        
        results = await retriever.aget_relevant_documents("test query")
        
        assert len(results) == 1
        mock_vector_store.similarity_search.assert_called_once_with(
            query="test query",
            k=3,
            filter_dict=None
        )
    
    @pytest.mark.asyncio
    async def test_default_search_kwargs(self, mock_vector_store):
        """Test retriever with default search kwargs."""
        retriever = OpenSearchRetriever(
            vector_store=mock_vector_store,
            search_kwargs={}
        )
        
        await retriever.get_relevant_documents("test query")
        
        mock_vector_store.similarity_search.assert_called_once_with(
            query="test query",
            k=8,  # Default value
            filter_dict=None
        )


@pytest.mark.asyncio
async def test_integration_workflow(mock_opensearch_client, mock_bedrock_embeddings):
    """Test complete workflow integration."""
    with patch('agent_core.vector_store.OpenSearch', return_value=mock_opensearch_client), \
         patch('agent_core.vector_store.BedrockEmbeddings', return_value=mock_bedrock_embeddings):
        
        # Create vector store
        store = OpenSearchVectorStore(
            opensearch_endpoint="https://test-opensearch.com",
            index_name="integration-test"
        )
        
        # Initialize
        await store.initialize()
        assert store._initialized is True
        
        # Add documents
        documents = [
            Document(page_content="Property definition 1", metadata={"id": "prop1"}),
            Document(page_content="Property definition 2", metadata={"id": "prop2"})
        ]
        doc_ids = await store.add_documents(documents)
        assert len(doc_ids) == 2
        
        # Search
        results = await store.similarity_search("property definition", k=2)
        assert len(results) == 1  # Based on mock response
        
        # Get count
        count = await store.get_document_count()
        assert count == 1
        
        # Health check
        health = await store.health_check()
        assert health["cluster_status"] == "green"
        
        # Create retriever
        retriever = store.as_retriever(search_kwargs={"k": 5})
        retriever_results = await retriever.get_relevant_documents("test query")
        assert len(retriever_results) == 1