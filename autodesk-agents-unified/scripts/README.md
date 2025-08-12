# Migration and Deployment Scripts

This directory contains comprehensive migration and deployment scripts for the Autodesk Agents Unified project. These scripts handle the complete lifecycle of migrating from standalone agents to the unified architecture, including deployment automation, monitoring setup, and recovery procedures.

## Scripts Overview

### 1. `migrate_data.py` - Data Migration Script
Migrates cache data from standalone agent implementations to the unified architecture.

**Features:**
- Migrates Model Properties agent cache (index files, properties)
- Prepares AEC Data Model cache for OpenSearch migration
- Migrates Model Derivatives SQLite databases
- Creates migration manifest for tracking
- Supports dry-run mode for testing

**Usage:**
```bash
python3 migrate_data.py \
  --source-dirs "../acc-model-props-assistant" "../aec-data-model-assistant" "../aps-model-derivs-assistant" \
  --target-dir "./cache" \
  --dry-run
```

### 2. `deploy_automation.py` - Advanced Deployment Automation
Provides comprehensive deployment automation with backup, rollback, monitoring, and horizontal scaling capabilities.

**Features:**
- Automated Docker image building and pushing
- Service deployment with health checks and scaling support
- Automatic backup creation before deployment
- Auto-rollback on deployment failure
- Horizontal scaling with load balancer setup
- Auto-scaling support for production environments
- Notification support via webhooks
- Deployment state tracking

**Usage:**
```bash
# Basic deployment
python3 deploy_automation.py \
  --environment production \
  --image-tag v1.0.0 \
  --registry your-registry.com \
  --notification-webhook https://hooks.slack.com/your-webhook

# Scaled deployment with load balancer
python3 deploy_automation.py \
  --environment production \
  --image-tag v1.0.0 \
  --scale 3 \
  --enable-load-balancer

# Auto-scaling deployment
python3 deploy_automation.py \
  --environment production \
  --enable-auto-scaling \
  --min-replicas 2 \
  --max-replicas 10
```

### 3. `setup_monitoring.py` - Monitoring and Alerting Setup
Sets up comprehensive monitoring infrastructure with Prometheus, Grafana, and Alertmanager.

**Features:**
- Prometheus configuration with custom metrics
- Grafana dashboards for system and agent monitoring
- Alert rules for critical system events
- Log aggregation with Fluentd
- Health check scripts
- Docker Compose setup for monitoring stack

**Usage:**
```bash
python3 setup_monitoring.py --environment production
```

### 4. `rollback_recovery.py` - Rollback and Recovery Management
Provides comprehensive rollback and disaster recovery capabilities.

**Features:**
- Emergency backup creation
- Rollback to specific deployments
- Restore from backups
- Backup cleanup and management
- Health verification after recovery
- Recovery operation tracking

**Usage:**
```bash
# List available deployments
python3 rollback_recovery.py --environment production list deployments

# Rollback to specific deployment
python3 rollback_recovery.py --environment production rollback deploy-1234567890

# Create emergency backup
python3 rollback_recovery.py --environment production backup

# Restore from backup
python3 rollback_recovery.py --environment production restore backup-1234567890
```

### 6. `auto_scaling.py` - Horizontal Auto-Scaling Management
Provides intelligent horizontal scaling based on system metrics and load patterns.

**Features:**
- Prometheus metrics-based scaling decisions
- CPU, memory, and response time monitoring
- Configurable scaling thresholds and cooldown periods
- Load balancer integration for scaled deployments
- Scaling metrics logging and history
- Production-ready auto-scaling daemon

**Usage:**
```bash
# Start auto-scaling with default settings
python3 auto_scaling.py --environment production

# Custom scaling configuration
python3 auto_scaling.py \
  --environment production \
  --min-replicas 2 \
  --max-replicas 10 \
  --target-cpu 70 \
  --target-memory 80 \
  --target-response-time 2000
```

### 7. `validate_deployment.py` - Comprehensive Deployment Validation
Validates that all three agent types are properly initialized and functioning correctly.

**Features:**
- Health checks for all agent types (Model Properties, AEC Data Model, Model Derivatives)
- API endpoint validation
- Metrics endpoint verification
- Backward compatibility testing
- Detailed validation reporting
- JSON output for CI/CD integration

**Usage:**
```bash
# Basic validation
python3 validate_deployment.py

# Custom validation with detailed output
python3 validate_deployment.py \
  --base-url http://localhost:8000 \
  --output validation_results.json \
  --wait-time 30 \
  --verbose
```

### 8. `deployment_status.py` - Deployment Status Dashboard
Provides real-time status dashboard for deployments, system health, and metrics.

**Features:**
- Real-time system health monitoring
- Agent status tracking
- Dependencies health checks
- System metrics display (CPU, memory, response times)
- Recent deployments overview
- Active alerts monitoring
- Docker containers status
- Continuous monitoring mode
- JSON export for integration

**Usage:**
```bash
# One-time status check
python3 deployment_status.py

# Continuous monitoring dashboard
python3 deployment_status.py --continuous --interval 30

# Save status to file
python3 deployment_status.py --output status.json

# Custom URLs
python3 deployment_status.py \
  --base-url http://localhost:8000 \
  --prometheus-url http://localhost:9090 \
  --alertmanager-url http://localhost:9093
```

### 9. `deployment_verification.py` - Comprehensive Deployment Verification
Performs extensive testing of all system components, integrations, and performance benchmarks.

**Features:**
- Comprehensive system health testing
- Agent functionality verification with real prompts
- Performance benchmarking under load
- Security headers and configuration checks
- API documentation availability testing
- Monitoring integration verification
- Docker environment validation
- Detailed test categorization and reporting
- Performance metrics collection
- Security assessment

**Usage:**
```bash
# Basic comprehensive verification
python3 deployment_verification.py

# Custom verification with detailed output
python3 deployment_verification.py \
  --base-url http://localhost:8000 \
  --output verification_results.json \
  --wait-time 30 \
  --verbose \
  --prometheus-url http://localhost:9090
```

### 5. `deployment_orchestrator.sh` - Comprehensive Deployment Orchestrator
Master script that orchestrates the complete deployment process including migration, deployment, monitoring, scaling, and recovery.

**Features:**
- Full deployment workflow automation
- Cache data migration integration
- Monitoring setup integration
- Horizontal scaling and auto-scaling support
- Comprehensive health check and validation
- Recovery and rollback capabilities
- Environment-specific configurations

**Usage:**
```bash
# Full deployment with migration
./deployment_orchestrator.sh full-deploy \
  --environment production \
  --source-dirs "../acc-model-props-assistant ../aec-data-model-assistant ../aps-model-derivs-assistant"

# Scaled deployment
./deployment_orchestrator.sh deploy \
  --environment production \
  --image-tag v1.0.0 \
  --scale 3 \
  --enable-lb

# Auto-scaling deployment
./deployment_orchestrator.sh deploy \
  --environment production \
  --enable-autoscale \
  --min-replicas 2 \
  --max-replicas 10

# Setup monitoring
./deployment_orchestrator.sh setup-monitoring --environment production

# Start auto-scaling service
./deployment_orchestrator.sh start-autoscale --min-replicas 2 --max-replicas 8

# Health check and validation
./deployment_orchestrator.sh health-check

# Status dashboard
./deployment_orchestrator.sh status

# Comprehensive verification
./deployment_orchestrator.sh verify

# Rollback
./deployment_orchestrator.sh rollback --deployment-id deploy-1234567890
```

## Directory Structure

After running the scripts, the following directory structure will be created:

```
autodesk-agents-unified/
├── scripts/                    # Deployment scripts
├── cache/                      # Migrated cache data
│   ├── model_properties/       # Model Properties cache
│   ├── aec_data_model/        # AEC Data Model cache
│   └── model_derivatives/     # Model Derivatives cache
├── deployments/               # Deployment tracking
│   └── deploy-*/              # Individual deployment records
├── backups/                   # System backups
│   └── backup-*/              # Individual backup archives
├── recovery/                  # Recovery operations log
├── monitoring/                # Monitoring configuration
│   ├── prometheus.yml         # Prometheus config
│   ├── alert_rules.yml        # Alert rules
│   ├── alertmanager.yml       # Alertmanager config
│   ├── grafana/               # Grafana dashboards
│   ├── scaling_metrics/       # Auto-scaling metrics
│   └── docker-compose.monitoring.yml
├── nginx/                     # Load balancer configuration
│   └── nginx.conf             # Nginx config for scaling
├── validation_results.json    # Deployment validation results
├── verification_results.json # Comprehensive verification results
├── deployment_status.json    # Current deployment status
├── autoscaling.log           # Auto-scaling daemon logs
├── autoscaling.pid           # Auto-scaling process ID
└── logs/                      # Application logs
```

## Environment Variables

The scripts support the following environment variables:

```bash
# Deployment environment
export ENVIRONMENT=production

# Docker configuration
export IMAGE_TAG=v1.0.0
export DOCKER_REGISTRY=your-registry.com

# Monitoring URLs
export HEALTH_URL=http://localhost:8000/health
export PROMETHEUS_URL=http://localhost:9090
export GRAFANA_URL=http://localhost:3000

# Notification
export NOTIFICATION_WEBHOOK=https://hooks.slack.com/your-webhook

# AWS Configuration (for production)
export AWS_REGION=us-east-1
export OPENSEARCH_ENDPOINT=https://your-opensearch-domain.us-east-1.es.amazonaws.com
export BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

## Prerequisites

### System Requirements
- Docker and Docker Compose
- Python 3.11+
- curl
- bash

### Python Dependencies
```bash
pip3 install requests pyyaml
```

### Docker Images
The scripts will automatically pull the following images:
- `prom/prometheus:latest`
- `grafana/grafana:latest`
- `prom/alertmanager:latest`
- `prom/node-exporter:latest`
- `fluent/fluentd:v1.16-debian-1`

## Deployment Workflows

### 1. Development Deployment
```bash
# Setup development environment
./deployment_orchestrator.sh full-deploy \
  --environment development \
  --source-dirs "../acc-model-props-assistant ../aec-data-model-assistant ../aps-model-derivs-assistant"
```

### 2. Production Deployment
```bash
# Production deployment with all features
export ENVIRONMENT=production
export IMAGE_TAG=v1.0.0
export DOCKER_REGISTRY=your-registry.com
export NOTIFICATION_WEBHOOK=https://hooks.slack.com/your-webhook

./deployment_orchestrator.sh full-deploy \
  --source-dirs "../acc-model-props-assistant ../aec-data-model-assistant ../aps-model-derivs-assistant"
```

### 3. Migration Only
```bash
# Migrate cache data without deployment
./deployment_orchestrator.sh migrate \
  --source-dirs "../acc-model-props-assistant ../aec-data-model-assistant ../aps-model-derivs-assistant" \
  --target-dir "./cache"
```

### 4. Emergency Rollback
```bash
# List available deployments
python3 rollback_recovery.py --environment production list deployments

# Rollback to previous deployment
./deployment_orchestrator.sh rollback --deployment-id deploy-1234567890
```

## Monitoring and Alerting

After deployment, the following monitoring services will be available:

- **Grafana**: http://localhost:3000 (admin/admin123)
  - Main dashboard with system metrics
  - Agent-specific dashboard with detailed metrics
  
- **Prometheus**: http://localhost:9090
  - Metrics collection and querying
  - Alert rule management
  
- **Alertmanager**: http://localhost:9093
  - Alert routing and notification

### Key Metrics Monitored
- HTTP request rate and response time
- Agent processing time and distribution
- Cache hit/miss rates
- System resource usage (CPU, memory, disk)
- Service health and availability
- Error rates and types

### Alert Conditions
- Service down (> 1 minute)
- High response time (> 2 seconds for 5 minutes)
- High error rate (> 10% for 5 minutes)
- High memory usage (> 1.5GB for 10 minutes)
- Dependency failures (OpenSearch, Redis down)
- Disk space usage (> 80%)

## Troubleshooting

### Common Issues

1. **Migration fails with permission errors**
   ```bash
   sudo chown -R $USER:$USER ./cache
   ```

2. **Docker build fails**
   ```bash
   docker system prune -f
   docker-compose down -v
   ```

3. **Health checks fail**
   ```bash
   # Check service logs
   docker-compose logs -f
   
   # Check individual service health
   curl -v http://localhost:8000/health
   ```

4. **Monitoring services not starting**
   ```bash
   # Check monitoring stack
   docker-compose -f monitoring/docker-compose.monitoring.yml logs
   
   # Restart monitoring
   docker-compose -f monitoring/docker-compose.monitoring.yml down
   docker-compose -f monitoring/docker-compose.monitoring.yml up -d
   ```

### Log Locations
- Application logs: `docker-compose logs`
- Deployment logs: `deployments/deploy-*/`
- Migration logs: Console output and migration manifest
- Recovery logs: `recovery/`

### Recovery Procedures

1. **Service failure during deployment**
   - Automatic rollback will be triggered if enabled
   - Manual rollback: `./deployment_orchestrator.sh rollback --deployment-id <id>`

2. **Data corruption**
   - Restore from backup: `python3 rollback_recovery.py restore <backup-id>`
   - Re-run migration: `./deployment_orchestrator.sh migrate`

3. **Complete system failure**
   - Emergency backup: `python3 rollback_recovery.py backup`
   - Full restore: `python3 rollback_recovery.py restore <backup-id>`

## Security Considerations

- All scripts validate input parameters
- Backup files are stored locally (consider encryption for production)
- Docker images are pulled from official repositories
- Health checks use local endpoints only
- Webhook notifications should use HTTPS

## Support

For issues with the migration and deployment scripts:

1. Check the troubleshooting section above
2. Review logs in the respective directories
3. Verify prerequisites are installed
4. Check environment variable configuration
5. Ensure Docker and Docker Compose are running properly