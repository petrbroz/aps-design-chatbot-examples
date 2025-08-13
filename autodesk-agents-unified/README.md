# Autodesk Agents Unified System

A unified agent system that integrates three specialized Autodesk agents with real external service integrations:

- **Model Properties Agent** - Elasticsearch integration for model property indexing and search
- **AEC Data Model Agent** - AWS OpenSearch integration with Bedrock embeddings for semantic search
- **Model Derivatives Agent** - SQLite database integration for model derivative data analysis

## 🏗️ Architecture

The system is built on the **AgentCore** framework, providing:

- **Unified Configuration** - YAML-based configuration with environment overrides
- **Centralized Authentication** - OAuth 2.0 integration with Autodesk Platform Services
- **Structured Logging** - JSON-formatted logs with trace IDs and metadata
- **Health Monitoring** - Comprehensive health checks and metrics
- **Tool Registry** - Centralized tool management and discovery
- **API Gateway** - FastAPI-based REST API with backward compatibility
- **Caching System** - Intelligent caching with TTL and invalidation

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Autodesk Platform Services credentials
- Access to Elasticsearch (for Model Properties)
- Access to AWS OpenSearch (for AEC Data Model)

### Installation

1. **Clone and setup:**
```bash
git clone <repository>
cd autodesk-agents-unified
pip install -r requirements.txt
```

2. **Configure environment:**
```bash
export AUTODESK_CLIENT_ID="your_client_id"
export AUTODESK_CLIENT_SECRET="your_client_secret"
export ELASTICSEARCH_URL="http://localhost:9200"
export OPENSEARCH_ENDPOINT="https://your-opensearch-domain.us-east-1.es.amazonaws.com"
export AWS_REGION="us-east-1"
```

3. **Deploy the system:**
```bash
python deploy.py production
```

4. **Start the server:**
```bash
python main.py
```

The system will be available at `http://localhost:8000` with API documentation at `/docs`.

## 🤖 Agents Overview

### Model Properties Agent

**Integration:** Elasticsearch  
**Purpose:** Index and search model properties with advanced querying capabilities

**Key Features:**
- Real-time property indexing
- Complex search queries with filters
- JQ query processing for data transformation
- Property statistics and aggregations

**Example Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/model-properties" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Create index for project ABC123",
    "context": {
      "project_id": "ABC123",
      "version_id": "v1.0"
    }
  }'
```

### AEC Data Model Agent

**Integration:** AWS OpenSearch + Bedrock Embeddings  
**Purpose:** Semantic search and analysis of AEC property definitions

**Key Features:**
- Vector embeddings using Amazon Bedrock
- Semantic similarity search
- GraphQL query execution
- Property definition relationships
- Real-time data synchronization

**Example Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/aec-data-model" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Find properties related to structural elements",
    "context": {
      "search_type": "semantic",
      "limit": 10
    }
  }'
```

### Model Derivatives Agent

**Integration:** SQLite Database  
**Purpose:** SQL-based analysis of model derivative data

**Key Features:**
- Automatic database schema creation
- Model data import from Autodesk API
- Complex SQL query execution
- Property analytics and reporting
- Data export capabilities

**Example Usage:**
```bash
curl -X POST "http://localhost:8000/api/v1/model-derivatives" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "SELECT category, COUNT(*) FROM elements GROUP BY category",
    "context": {
      "project_id": "ABC123",
      "version_id": "v1.0"
    }
  }'
```

## 🧪 Testing

### Run Individual Agent Tests

```bash
# Test Model Properties Agent
python test_model_properties_agent.py

# Test AEC Data Model Agent  
python test_aec_data_model_agent.py

# Test Model Derivatives Agent
python test_model_derivatives_agent.py
```

### Run All Tests

```bash
python test_all_agents.py
```

### Test API Endpoints

```bash
# Health check
curl http://localhost:8000/health

# Test Model Properties endpoint
curl -X POST "http://localhost:8000/api/v1/model-properties" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "help", "context": {}}'

# Test AEC Data Model endpoint
curl -X POST "http://localhost:8000/api/v1/aec-data-model" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "help", "context": {}}'

# Test Model Derivatives endpoint
curl -X POST "http://localhost:8000/api/v1/model-derivatives" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "help", "context": {}}'
```

## 📊 Monitoring and Logging

### Health Monitoring

The system provides comprehensive health monitoring:

- **System Health:** `/health` endpoint
- **Agent Health:** Individual agent status
- **Dependency Health:** External service connectivity
- **Performance Metrics:** Response times and throughput

### Structured Logging

All logs are structured in JSON format with:

- **Trace IDs:** Request correlation
- **Metadata:** Context and performance data
- **Error Details:** Stack traces and error codes
- **Agent Context:** Agent-specific information

Logs are written to:
- Console (development)
- `logs/agent_core.log` (production)

### Example Log Entry

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "message": "Agent request processed successfully",
  "trace_id": "abc123-def456-ghi789",
  "agent_type": "model_properties",
  "request_id": "req_001",
  "user_id": "user_123",
  "duration_ms": 245,
  "metadata": {
    "project_id": "ABC123",
    "operation": "create_index",
    "results_count": 1500
  }
}
```

## 🔧 Configuration

### Main Configuration (`config/config.yaml`)

```yaml
# Core system configuration
core:
  name: "Autodesk Agents Unified"
  version: "1.0.0"
  environment: "production"

# API Gateway settings
api:
  host: "0.0.0.0"
  port: 8000
  cors_origins: ["*"]
  max_request_size: 10485760

# Authentication
auth:
  autodesk:
    base_url: "https://developer.api.autodesk.com"
    token_url: "https://developer.api.autodesk.com/authentication/v1/authenticate"

# Logging configuration
logging:
  level: "INFO"
  format: "json"
  file: "logs/agent_core.log"
  max_size: "100MB"
  backup_count: 5

# Caching
cache:
  directory: "./cache"
  default_ttl: 3600
  max_size: "1GB"

# Health monitoring
health:
  check_interval: 30
  timeout: 10
  dependencies:
    - elasticsearch
    - opensearch
    - autodesk_api
```

### Environment-Specific Configuration

Create environment-specific configs in `config/`:

- `config/development.yaml`
- `config/staging.yaml`
- `config/production.yaml`

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AUTODESK_CLIENT_ID` | Autodesk Platform Services Client ID | Required |
| `AUTODESK_CLIENT_SECRET` | Autodesk Platform Services Client Secret | Required |
| `ELASTICSEARCH_URL` | Elasticsearch endpoint URL | `http://localhost:9200` |
| `OPENSEARCH_ENDPOINT` | AWS OpenSearch endpoint | Required for AEC agent |
| `AWS_REGION` | AWS region for OpenSearch | `us-east-1` |
| `PORT` | Server port | `8000` |
| `HOST` | Server host | `0.0.0.0` |
| `LOG_LEVEL` | Logging level | `info` |
| `ENVIRONMENT` | Deployment environment | `production` |

## 🐳 Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t autodesk-agents-unified .

# Run the container
docker run -p 8000:8000 \
  -e AUTODESK_CLIENT_ID="your_client_id" \
  -e AUTODESK_CLIENT_SECRET="your_client_secret" \
  -e ELASTICSEARCH_URL="http://host.docker.internal:9200" \
  autodesk-agents-unified
```

### Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## 🔒 Security

### Authentication

- OAuth 2.0 integration with Autodesk Platform Services
- Token-based authentication for all API calls
- Automatic token refresh and caching

### Data Security

- Secure credential storage using environment variables
- Input validation and sanitization
- SQL injection prevention for database queries
- CORS configuration for web security

### Network Security

- HTTPS support for production deployments
- Rate limiting and request size limits
- Health check endpoints for load balancers

## 📈 Performance

### Optimization Features

- **Intelligent Caching:** Multi-level caching with TTL
- **Connection Pooling:** Efficient database connections
- **Async Processing:** Non-blocking I/O operations
- **Request Batching:** Bulk operations where possible

### Performance Metrics

- **Response Times:** < 500ms for cached queries
- **Throughput:** 100+ requests/second per agent
- **Memory Usage:** < 512MB base memory footprint
- **CPU Usage:** < 50% under normal load

## 🛠️ Development

### Project Structure

```
autodesk-agents-unified/
├── agentcore/              # Core framework
│   ├── __init__.py
│   ├── agent_core.py       # Main AgentCore class
│   ├── base_agent.py       # Base agent interface
│   ├── orchestrator.py     # Agent orchestration
│   ├── api_gateway.py      # FastAPI gateway
│   ├── auth.py            # Authentication
│   ├── config.py          # Configuration management
│   ├── logging.py         # Structured logging
│   ├── health.py          # Health monitoring
│   ├── cache.py           # Caching system
│   └── tools/             # Tool framework
├── agents/                # Agent implementations
│   ├── __init__.py
│   ├── model_properties.py
│   ├── aec_data_model.py
│   └── model_derivatives.py
├── config/                # Configuration files
├── tests/                 # Test files
├── logs/                  # Log files
├── cache/                 # Cache directory
├── requirements.txt       # Dependencies
├── main.py               # Application entry point
├── deploy.py             # Deployment script
└── README.md             # This file
```

### Adding New Agents

1. **Create agent class:**
```python
from agentcore import BaseAgent, AgentRequest, AgentResponse

class MyAgent(BaseAgent):
    async def process_prompt(self, request: AgentRequest, context: ExecutionContext) -> AgentResponse:
        # Implementation here
        pass
```

2. **Register with orchestrator:**
```python
orchestrator.register_agent("my_agent", my_agent_instance)
```

3. **Add API endpoint:**
```python
@app.post("/api/v1/my-agent")
async def my_agent_endpoint(request: AgentRequest):
    return await orchestrator.route_request("my_agent", request)
```

### Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📚 API Reference

### Common Request Format

```json
{
  "prompt": "User prompt or command",
  "context": {
    "project_id": "optional_project_id",
    "version_id": "optional_version_id",
    "user_id": "optional_user_id",
    "additional_params": "value"
  }
}
```

### Common Response Format

```json
{
  "success": true,
  "responses": [
    "Response line 1",
    "Response line 2"
  ],
  "metadata": {
    "agent_type": "model_properties",
    "request_id": "req_123",
    "duration_ms": 245,
    "additional_info": "value"
  },
  "error_message": null,
  "error_code": null
}
```

### Error Response Format

```json
{
  "success": false,
  "responses": [],
  "metadata": {
    "agent_type": "model_properties",
    "request_id": "req_123",
    "duration_ms": 100
  },
  "error_message": "Detailed error description",
  "error_code": "VALIDATION_ERROR"
}
```

## 🆘 Troubleshooting

### Common Issues

**1. Authentication Errors**
```
Error: Invalid client credentials
Solution: Check AUTODESK_CLIENT_ID and AUTODESK_CLIENT_SECRET
```

**2. Elasticsearch Connection**
```
Error: Connection refused to Elasticsearch
Solution: Ensure Elasticsearch is running and accessible at ELASTICSEARCH_URL
```

**3. OpenSearch Access**
```
Error: Access denied to OpenSearch
Solution: Check AWS credentials and OpenSearch domain permissions
```

**4. Database Errors**
```
Error: SQLite database locked
Solution: Check file permissions and ensure no other processes are using the database
```

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=debug
python main.py
```

### Health Checks

Check system health:
```bash
curl http://localhost:8000/health
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Support

For support and questions:

1. Check the troubleshooting section
2. Review the API documentation at `/docs`
3. Check the logs in `logs/agent_core.log`
4. Create an issue in the repository

---

**Built with ❤️ for the Autodesk Developer Community**