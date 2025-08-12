#!/bin/bash

# Deployment Orchestrator for Autodesk Agents Unified
# Comprehensive deployment management with migration, monitoring, and recovery
set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT=${ENVIRONMENT:-development}
IMAGE_TAG=${IMAGE_TAG:-latest}
CONFIG_FILE="$SCRIPT_DIR/deployment_config.yaml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
Deployment Orchestrator for Autodesk Agents Unified

Usage: $0 [COMMAND] [OPTIONS]

Commands:
    migrate         Migrate cache data from standalone agents
    deploy          Deploy the unified agent system
    rollback        Rollback to previous deployment
    restore         Restore from backup
    setup-monitoring Setup monitoring and alerting
    start-autoscale Start auto-scaling service
    health-check    Run comprehensive health checks
    status          Show deployment status dashboard
    verify          Run comprehensive deployment verification
    cleanup         Clean up old deployments and backups
    full-deploy     Complete deployment with migration and monitoring

Options:
    --environment   Environment (development|production) [default: development]
    --image-tag     Docker image tag [default: latest]
    --source-dirs   Source directories for migration (space-separated)
    --target-dir    Target directory for migration
    --deployment-id Deployment ID for rollback
    --backup-id     Backup ID for restore
    --scale         Number of replicas to deploy [default: 1]
    --enable-lb     Enable load balancer for scaled deployments
    --enable-autoscale Enable auto-scaling (production only)
    --min-replicas  Minimum replicas for auto-scaling [default: 1]
    --max-replicas  Maximum replicas for auto-scaling [default: 5]
    --dry-run       Perform dry run without actual changes
    --help          Show this help message

Environment Variables:
    ENVIRONMENT     Deployment environment
    IMAGE_TAG       Docker image tag
    DOCKER_REGISTRY Docker registry URL
    NOTIFICATION_WEBHOOK Webhook URL for notifications

Examples:
    # Full deployment with migration
    $0 full-deploy --environment production --source-dirs "../acc-model-props-assistant ../aec-data-model-assistant ../aps-model-derivs-assistant"
    
    # Migrate cache data only
    $0 migrate --source-dirs "../acc-model-props-assistant ../aec-data-model-assistant" --target-dir "./cache"
    
    # Deploy to production with scaling
    $0 deploy --environment production --image-tag v1.0.0 --scale 3 --enable-lb
    
    # Deploy with auto-scaling
    $0 deploy --environment production --enable-autoscale --min-replicas 2 --max-replicas 10
    
    # Setup monitoring
    $0 setup-monitoring --environment production
    
    # Rollback deployment
    $0 rollback --deployment-id deploy-1234567890
    
    # Health check
    $0 health-check
    
    # Status dashboard
    $0 status
    
    # Comprehensive verification
    $0 verify

EOF
}

# Parse command line arguments
parse_args() {
    COMMAND=""
    SOURCE_DIRS=""
    TARGET_DIR=""
    DEPLOYMENT_ID=""
    BACKUP_ID=""
    DRY_RUN=""
    SCALE_REPLICAS="1"
    ENABLE_LB=""
    ENABLE_AUTOSCALE=""
    MIN_REPLICAS="1"
    MAX_REPLICAS="5"
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            migrate|deploy|rollback|restore|setup-monitoring|start-autoscale|health-check|status|verify|cleanup|full-deploy)
                COMMAND="$1"
                shift
                ;;
            --environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            --image-tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            --source-dirs)
                SOURCE_DIRS="$2"
                shift 2
                ;;
            --target-dir)
                TARGET_DIR="$2"
                shift 2
                ;;
            --deployment-id)
                DEPLOYMENT_ID="$2"
                shift 2
                ;;
            --backup-id)
                BACKUP_ID="$2"
                shift 2
                ;;
            --scale)
                SCALE_REPLICAS="$2"
                shift 2
                ;;
            --enable-lb)
                ENABLE_LB="--enable-load-balancer"
                shift
                ;;
            --enable-autoscale)
                ENABLE_AUTOSCALE="--enable-auto-scaling"
                shift
                ;;
            --min-replicas)
                MIN_REPLICAS="$2"
                shift 2
                ;;
            --max-replicas)
                MAX_REPLICAS="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN="--dry-run"
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    if [[ -z "$COMMAND" ]]; then
        log_error "No command specified"
        show_help
        exit 1
    fi
}

# Load deployment configuration
load_deployment_config() {
    log_step "Loading deployment configuration..."
    
    if [[ -f "$CONFIG_FILE" ]]; then
        log_info "Loading configuration from $CONFIG_FILE"
        
        # Load configuration and export environment variables
        if python3 "$SCRIPT_DIR/config_loader.py" --environment "$ENVIRONMENT" --config-file "$CONFIG_FILE" --export-env > /tmp/deployment_env.sh; then
            source /tmp/deployment_env.sh
            rm -f /tmp/deployment_env.sh
            log_info "Configuration loaded successfully"
        else
            log_warn "Failed to load configuration, using defaults"
        fi
    else
        log_warn "Configuration file not found, using defaults"
    fi
}

# Validate prerequisites
validate_prerequisites() {
    log_step "Validating prerequisites..."
    
    # Check required tools
    local required_tools=("docker" "docker-compose" "python3" "curl")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            log_error "$tool is not installed or not in PATH"
            exit 1
        fi
    done
    
    # Check Python dependencies
    if ! python3 -c "import requests, yaml" &> /dev/null; then
        log_warn "Installing required Python packages..."
        pip3 install requests pyyaml
    fi
    
    # Validate environment
    if [[ "$ENVIRONMENT" != "development" && "$ENVIRONMENT" != "production" && "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "testing" ]]; then
        log_error "Invalid environment: $ENVIRONMENT (must be development, staging, production, or testing)"
        exit 1
    fi
    
    log_info "Prerequisites validation passed"
}

# Migrate cache data
migrate_cache_data() {
    log_step "Migrating cache data..."
    
    if [[ -z "$SOURCE_DIRS" ]]; then
        log_error "Source directories not specified for migration"
        exit 1
    fi
    
    local target_dir="${TARGET_DIR:-$PROJECT_ROOT/cache}"
    
    log_info "Migrating from: $SOURCE_DIRS"
    log_info "Migrating to: $target_dir"
    
    python3 "$SCRIPT_DIR/migrate_data.py" \
        --source-dirs $SOURCE_DIRS \
        --target-dir "$target_dir" \
        $DRY_RUN \
        --verbose
    
    if [[ $? -eq 0 ]]; then
        log_info "Cache migration completed successfully"
    else
        log_error "Cache migration failed"
        exit 1
    fi
}

# Deploy the system
deploy_system() {
    log_step "Deploying Autodesk Agents Unified..."
    
    local deploy_args=(
        "--environment" "$ENVIRONMENT"
        "--image-tag" "$IMAGE_TAG"
        "--scale" "$SCALE_REPLICAS"
        "--min-replicas" "$MIN_REPLICAS"
        "--max-replicas" "$MAX_REPLICAS"
    )
    
    if [[ -n "$DOCKER_REGISTRY" ]]; then
        deploy_args+=("--registry" "$DOCKER_REGISTRY")
    fi
    
    if [[ -n "$NOTIFICATION_WEBHOOK" ]]; then
        deploy_args+=("--notification-webhook" "$NOTIFICATION_WEBHOOK")
    fi
    
    if [[ -n "$ENABLE_LB" ]]; then
        deploy_args+=("$ENABLE_LB")
    fi
    
    if [[ -n "$ENABLE_AUTOSCALE" ]]; then
        deploy_args+=("$ENABLE_AUTOSCALE")
    fi
    
    python3 "$SCRIPT_DIR/deploy_automation.py" "${deploy_args[@]}"
    
    if [[ $? -eq 0 ]]; then
        log_info "Deployment completed successfully"
    else
        log_error "Deployment failed"
        exit 1
    fi
}

# Setup monitoring
setup_monitoring() {
    log_step "Setting up monitoring and alerting..."
    
    python3 "$SCRIPT_DIR/setup_monitoring.py" \
        --environment "$ENVIRONMENT" \
        --config-dir "$PROJECT_ROOT/monitoring"
    
    if [[ $? -eq 0 ]]; then
        log_info "Monitoring setup completed successfully"
        
        # Start monitoring stack
        log_info "Starting monitoring stack..."
        cd "$PROJECT_ROOT"
        docker-compose -f monitoring/docker-compose.monitoring.yml up -d
        
        log_info "Monitoring services started:"
        log_info "  - Grafana: http://localhost:3000 (admin/admin123)"
        log_info "  - Prometheus: http://localhost:9090"
        log_info "  - Alertmanager: http://localhost:9093"
    else
        log_error "Monitoring setup failed"
        exit 1
    fi
}

# Run health checks
run_health_checks() {
    log_step "Running comprehensive health checks..."
    
    # Wait for services to be ready
    log_info "Waiting for services to be ready..."
    sleep 10
    
    # Run comprehensive deployment validation
    log_info "Running deployment validation..."
    python3 "$SCRIPT_DIR/validate_deployment.py" \
        --base-url "http://localhost:8000" \
        --wait-time 30 \
        --output "$PROJECT_ROOT/validation_results.json" \
        --verbose
    
    local validation_result=$?
    
    # Also run basic health check script if it exists
    local health_script="$PROJECT_ROOT/monitoring/health_check.sh"
    if [[ -f "$health_script" ]]; then
        log_info "Running additional health checks..."
        bash "$health_script"
        local health_result=$?
    else
        local health_result=0
    fi
    
    if [[ $validation_result -eq 0 && $health_result -eq 0 ]]; then
        log_info "All health checks and validation passed"
    else
        log_error "Health checks or validation failed"
        log_error "Check validation_results.json for detailed results"
        exit 1
    fi
}

# Show deployment status dashboard
show_deployment_status() {
    log_step "Showing deployment status dashboard..."
    
    python3 "$SCRIPT_DIR/deployment_status.py" \
        --base-url "http://localhost:8000" \
        --output "$PROJECT_ROOT/deployment_status.json"
    
    if [[ $? -eq 0 ]]; then
        log_info "Deployment status retrieved successfully"
    else
        log_error "Failed to retrieve deployment status"
        exit 1
    fi
}

# Run comprehensive deployment verification
run_deployment_verification() {
    log_step "Running comprehensive deployment verification..."
    
    python3 "$SCRIPT_DIR/deployment_verification.py" \
        --base-url "http://localhost:8000" \
        --wait-time 30 \
        --output "$PROJECT_ROOT/verification_results.json" \
        --verbose
    
    if [[ $? -eq 0 ]]; then
        log_info "Comprehensive verification passed"
    else
        log_error "Comprehensive verification failed"
        log_error "Check verification_results.json for detailed results"
        exit 1
    fi
}

# Rollback deployment
rollback_deployment() {
    log_step "Rolling back deployment..."
    
    if [[ -z "$DEPLOYMENT_ID" ]]; then
        log_error "Deployment ID not specified for rollback"
        exit 1
    fi
    
    python3 "$SCRIPT_DIR/rollback_recovery.py" \
        --environment "$ENVIRONMENT" \
        rollback "$DEPLOYMENT_ID"
    
    if [[ $? -eq 0 ]]; then
        log_info "Rollback completed successfully"
        run_health_checks
    else
        log_error "Rollback failed"
        exit 1
    fi
}

# Restore from backup
restore_from_backup() {
    log_step "Restoring from backup..."
    
    if [[ -z "$BACKUP_ID" ]]; then
        log_error "Backup ID not specified for restore"
        exit 1
    fi
    
    python3 "$SCRIPT_DIR/rollback_recovery.py" \
        --environment "$ENVIRONMENT" \
        restore "$BACKUP_ID"
    
    if [[ $? -eq 0 ]]; then
        log_info "Restore completed successfully"
        run_health_checks
    else
        log_error "Restore failed"
        exit 1
    fi
}

# Start auto-scaling service
start_autoscaling() {
    log_step "Starting auto-scaling service..."
    
    local autoscale_args=(
        "--environment" "$ENVIRONMENT"
        "--min-replicas" "$MIN_REPLICAS"
        "--max-replicas" "$MAX_REPLICAS"
    )
    
    # Start auto-scaling in background
    log_info "Starting auto-scaling daemon..."
    nohup python3 "$SCRIPT_DIR/auto_scaling.py" "${autoscale_args[@]}" > autoscaling.log 2>&1 &
    
    local autoscale_pid=$!
    echo $autoscale_pid > autoscaling.pid
    
    log_info "Auto-scaling started with PID: $autoscale_pid"
    log_info "Logs: tail -f autoscaling.log"
    log_info "Stop: kill \$(cat autoscaling.pid)"
}

# Cleanup old deployments and backups
cleanup_old_data() {
    log_step "Cleaning up old deployments and backups..."
    
    python3 "$SCRIPT_DIR/rollback_recovery.py" \
        --environment "$ENVIRONMENT" \
        cleanup --keep 10
    
    # Clean up old Docker images
    log_info "Cleaning up old Docker images..."
    docker image prune -f
    
    # Clean up old containers
    log_info "Cleaning up old containers..."
    docker container prune -f
    
    log_info "Cleanup completed"
}

# Full deployment process
full_deployment() {
    log_step "Starting full deployment process..."
    
    # Load deployment configuration
    load_deployment_config
    
    # Validate prerequisites
    validate_prerequisites
    
    # Migrate cache data if source directories provided
    if [[ -n "$SOURCE_DIRS" ]]; then
        migrate_cache_data
    else
        log_warn "No source directories specified, skipping cache migration"
    fi
    
    # Deploy the system
    deploy_system
    
    # Setup monitoring
    setup_monitoring
    
    # Run health checks
    run_health_checks
    
    # Run comprehensive verification
    log_info "Running comprehensive deployment verification..."
    run_deployment_verification
    
    # Show deployment summary
    show_deployment_summary
    
    log_info "Full deployment completed successfully!"
}

# Show deployment summary
show_deployment_summary() {
    log_step "Deployment Summary"
    
    echo ""
    echo "🚀 Autodesk Agents Unified Deployment Complete!"
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo "Image Tag: $IMAGE_TAG"
    echo ""
    echo "Services:"
    echo "  📊 Main Application: http://localhost:8000"
    echo "  📈 Grafana Dashboard: http://localhost:3000 (admin/admin123)"
    echo "  🔍 Prometheus: http://localhost:9090"
    echo "  🚨 Alertmanager: http://localhost:9093"
    echo ""
    echo "Health Check: curl http://localhost:8000/health"
    echo "API Documentation: http://localhost:8000/docs"
    echo ""
    echo "Logs: docker-compose logs -f"
    echo "Stop: docker-compose down"
    echo ""
}

# Main execution
main() {
    cd "$PROJECT_ROOT"
    
    case "$COMMAND" in
        migrate)
            validate_prerequisites
            migrate_cache_data
            ;;
        deploy)
            validate_prerequisites
            deploy_system
            run_health_checks
            ;;
        rollback)
            rollback_deployment
            ;;
        restore)
            restore_from_backup
            ;;
        setup-monitoring)
            setup_monitoring
            ;;
        start-autoscale)
            start_autoscaling
            ;;
        health-check)
            run_health_checks
            ;;
        status)
            show_deployment_status
            ;;
        verify)
            run_deployment_verification
            ;;
        cleanup)
            cleanup_old_data
            ;;
        full-deploy)
            full_deployment
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# Parse arguments and run main function
parse_args "$@"
main