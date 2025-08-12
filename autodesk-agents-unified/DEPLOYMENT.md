# Deployment Guide

This guide covers deployment options for the Autodesk Agents Unified application.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Development Deployment](#development-deployment)
- [Production Deployment](#production-deployment)
- [Docker Images](#docker-images)
- [Environment Variables](#environment-variables)
- [Health Checks](#health-checks)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- Docker 20.10+
- Docker Compose 2.0+
- curl (for health checks)

### AWS Requirements

- AWS account with appropriate permissions
- Bedrock access enabled
- OpenSearch Service cluster (for production)

## Configuration

### Environment-Specific Configurations

The application supports multiple configuration files:

- `config/development.yaml` - Development environment
- `config/production.yaml` - Production environment  
- `config/local.yaml` - Local overrides

### Configuration Priority

1. Environment variables (highest priority)
2. Configuration file specified by `AGENT_CONFIG_PATH`
3. Default configuration files in order: `config.yaml`, `production.yaml`, `development.yaml`

## Development Deployment

### Quick Start

1. **Set up development environment:**
   ```bash
   ./scripts/setup-dev.sh setup
   ```

2. **Start supporting services:**
   ```bash
   ./scripts/setup-dev.sh start
   ```

3. **Run the application:**
   ```bash
   python -m uvicorn agent_core.main:app --reload
   ```

### Using Docker Compose

1. **Start all services:**
   ```bash
   docker-compose up -d
   ```

2. **View logs:**
   ```bash
   docker-compose logs -f agents-unified
   ```

3. **Stop services:**
   ```bash
   docker-compose down
   ```

### Development Services

The development setup includes:

- **agents-unified**: Main application (port 8000)
- **opensearch**: Vector database (port 9200)
- **opensearch-dashboards**: OpenSearch UI (port 5601)
- **localstack**: AWS services simulation (port 4566)
- **redis**: Caching (port 6379)

## Production Deployment

### Using Docker Compose

1. **Set environment variables:**
   ```bash
   export AWS_REGION=us-east-1
   export OPENSEARCH_ENDPOINT=https://your-opensearch-cluster.region.es.amazonaws.com
   export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
   ```

2. **Deploy:**
   ```bash
   ./scripts/deploy.sh production
   ```

### Using Docker Swarm

1. **Initialize swarm:**
   ```bash
   docker swarm init
   ```

2. **Deploy stack:**
   ```bash
   docker stack deploy -c docker-compose.prod.yml agents-stack
   ```

### Manual Production Setup

1. **Build production image:**
   ```bash
   docker build --target production -t agents-unified:prod .
   ```

2. **Run with production config:**
   ```bash
   docker run -d \
     --name agents-unified \
     -p 8000:8000 \
     -e AGENT_CONFIG_PATH=/app/config/production.yaml \
     -e AWS_REGION=us-east-1 \
     -e OPENSEARCH_ENDPOINT=https://your-cluster.region.es.amazonaws.com \
     -v /app/cache:/app/cache \
     agents-unified:prod
   ```

## Docker Images

### Multi-Stage Build Targets

- **base**: Base Python environment with system dependencies
- **dependencies**: Base + Python packages installed
- **development**: Dependencies + development tools + source code
- **production**: Dependencies + optimized production setup
- **testing**: Development + test execution

### Building Specific Targets

```bash
# Development image
docker build --target development -t agents-unified:dev .

# Production image
docker build --target production -t agents-unified:prod .

# Testing image
docker build --target testing -t agents-unified:test .
```

## Environment Variables

### Core Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AGENT_CONFIG_PATH` | Path to configuration file | auto-detected | No |
| `AWS_REGION` | AWS region | us-east-1 | Yes |
| `BEDROCK_MODEL_ID` | Bedrock model identifier | anthropic.claude-3-5-sonnet-20241022-v2:0 | Yes |
| `OPENSEARCH_ENDPOINT` | OpenSearch cluster endpoint | - | Yes |
| `CACHE_DIRECTORY` | Cache storage directory | /tmp/agent_cache | No |
| `LOG_LEVEL` | Logging level | INFO | No |
| `AUTH_ENABLED` | Enable authentication | true | No |
| `HEALTH_CHECK_INTERVAL` | Health check interval (seconds) | 30 | No |

### Docker Registry

| Variable | Description | Example |
|----------|-------------|---------|
| `DOCKER_REGISTRY` | Docker registry URL | registry.company.com |
| `IMAGE_TAG` | Image tag | v1.0.0 |

## Health Checks

### Application Health

The application exposes a health check endpoint:

```bash
curl http://localhost:8000/health
```

Response format:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "version": "1.0.0",
  "dependencies": {
    "opensearch": "healthy",
    "bedrock": "healthy"
  }
}
```

### Docker Health Checks

Docker containers include built-in health checks:

```bash
# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}"

# View health check logs
docker inspect --format='{{json .State.Health}}' container_name
```

## Monitoring

### Logs

#### Development
```bash
# Application logs
docker-compose logs -f agents-unified

# All services
docker-compose logs -f
```

#### Production
```bash
# Docker Swarm
docker service logs -f agents-stack_agents-unified

# Individual container
docker logs -f container_name
```

### Metrics

The application exposes metrics at `/metrics` endpoint (Prometheus format).

### Log Aggregation

Production setup includes Fluentd for log aggregation:

```yaml
# fluentd.conf example
<source>
  @type forward
  port 24224
</source>

<match **>
  @type elasticsearch
  host opensearch
  port 9200
  index_name application-logs
</match>
```

## Troubleshooting

### Common Issues

#### 1. OpenSearch Connection Failed

**Symptoms:**
- Health check fails
- Vector search errors

**Solutions:**
```bash
# Check OpenSearch connectivity
curl http://localhost:9200/_cluster/health

# Verify environment variable
echo $OPENSEARCH_ENDPOINT

# Check container logs
docker-compose logs opensearch
```

#### 2. Authentication Errors

**Symptoms:**
- 401 Unauthorized responses
- Token validation failures

**Solutions:**
```bash
# Disable auth for testing
export AUTH_ENABLED=false

# Check token format
curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost:8000/health
```

#### 3. Memory Issues

**Symptoms:**
- Container restarts
- Out of memory errors

**Solutions:**
```bash
# Increase container memory
docker run --memory=2g agents-unified:prod

# Monitor memory usage
docker stats
```

#### 4. Configuration Issues

**Symptoms:**
- Application fails to start
- Configuration validation errors

**Solutions:**
```bash
# Validate configuration
python -c "from agent_core.config import ConfigManager; cm = ConfigManager(); print(cm.validate_config())"

# Check configuration summary
python -c "from agent_core.config import ConfigManager; cm = ConfigManager(); print(cm.get_config_summary())"
```

### Debugging Commands

```bash
# Enter running container
docker exec -it container_name /bin/bash

# Check application status
curl http://localhost:8000/health

# View configuration
curl http://localhost:8000/config/summary

# Test specific agent
curl -X POST http://localhost:8000/agents/model_properties/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test", "context": {}}'
```

### Log Analysis

```bash
# Filter error logs
docker-compose logs agents-unified | grep ERROR

# Monitor real-time logs
docker-compose logs -f --tail=100 agents-unified

# Export logs for analysis
docker-compose logs --no-color agents-unified > application.log
```

## Rollback Procedures

### Automatic Rollback

The deployment script includes automatic rollback on health check failure:

```bash
./scripts/deploy.sh production
# Automatically rolls back if health checks fail
```

### Manual Rollback

```bash
# Using deployment script
./scripts/deploy.sh rollback

# Manual Docker commands
docker tag agents-unified:previous agents-unified:latest
docker-compose -f docker-compose.prod.yml up -d
```

## Security Considerations

### Production Checklist

- [ ] Enable HTTPS with valid SSL certificates
- [ ] Configure authentication (`AUTH_ENABLED=true`)
- [ ] Set up proper firewall rules
- [ ] Use secrets management for sensitive configuration
- [ ] Enable audit logging
- [ ] Regular security updates
- [ ] Network segmentation
- [ ] Resource limits configured

### SSL/TLS Setup

1. **Obtain SSL certificates:**
   ```bash
   # Using Let's Encrypt
   certbot certonly --standalone -d your-domain.com
   ```

2. **Update nginx configuration:**
   ```nginx
   ssl_certificate /etc/nginx/ssl/cert.pem;
   ssl_certificate_key /etc/nginx/ssl/key.pem;
   ```

3. **Mount certificates in Docker:**
   ```yaml
   volumes:
     - /etc/letsencrypt/live/your-domain.com:/etc/nginx/ssl:ro
   ```

## Performance Tuning

### Resource Allocation

```yaml
# docker-compose.prod.yml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 4G
    reservations:
      cpus: '1.0'
      memory: 2G
```

### Scaling

```bash
# Scale application instances
docker-compose -f docker-compose.prod.yml up -d --scale agents-unified=3

# Docker Swarm scaling
docker service scale agents-stack_agents-unified=3
```

### Caching Optimization

- Configure Redis for distributed caching
- Tune cache TTL values in configuration
- Monitor cache hit rates

## Backup and Recovery

### Data Backup

```bash
# Backup cache data
docker run --rm -v agents_cache_data:/data -v $(pwd):/backup alpine tar czf /backup/cache-backup.tar.gz /data

# Backup configuration
cp -r config/ backup/config-$(date +%Y%m%d)/
```

### Disaster Recovery

1. **Restore from backup:**
   ```bash
   docker run --rm -v agents_cache_data:/data -v $(pwd):/backup alpine tar xzf /backup/cache-backup.tar.gz -C /
   ```

2. **Redeploy application:**
   ```bash
   ./scripts/deploy.sh production
   ```

For additional support, refer to the application logs and health check endpoints.