#!/bin/bash

# Deployment script for Autodesk Agents Unified
set -e

# Configuration
ENVIRONMENT=${1:-development}
DOCKER_REGISTRY=${DOCKER_REGISTRY:-""}
IMAGE_TAG=${IMAGE_TAG:-"latest"}
SERVICE_NAME="autodesk-agents-unified"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Build Docker image
build_image() {
    log_info "Building Docker image for $ENVIRONMENT environment..."
    
    if [ "$ENVIRONMENT" = "production" ]; then
        TARGET="production"
    else
        TARGET="development"
    fi
    
    docker build \
        --target $TARGET \
        --tag $SERVICE_NAME:$IMAGE_TAG \
        --tag $SERVICE_NAME:latest \
        .
    
    if [ ! -z "$DOCKER_REGISTRY" ]; then
        docker tag $SERVICE_NAME:$IMAGE_TAG $DOCKER_REGISTRY/$SERVICE_NAME:$IMAGE_TAG
        log_info "Tagged image for registry: $DOCKER_REGISTRY/$SERVICE_NAME:$IMAGE_TAG"
    fi
    
    log_info "Docker image built successfully"
}

# Push to registry
push_image() {
    if [ ! -z "$DOCKER_REGISTRY" ]; then
        log_info "Pushing image to registry..."
        docker push $DOCKER_REGISTRY/$SERVICE_NAME:$IMAGE_TAG
        log_info "Image pushed successfully"
    else
        log_warn "No registry specified, skipping push"
    fi
}

# Deploy with Docker Compose
deploy_compose() {
    log_info "Deploying with Docker Compose..."
    
    if [ "$ENVIRONMENT" = "production" ]; then
        COMPOSE_FILE="docker-compose.prod.yml"
    else
        COMPOSE_FILE="docker-compose.yml"
    fi
    
    # Check if compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "Compose file $COMPOSE_FILE not found"
        exit 1
    fi
    
    # Stop existing services
    log_info "Stopping existing services..."
    docker-compose -f $COMPOSE_FILE down --remove-orphans
    
    # Start services
    log_info "Starting services..."
    docker-compose -f $COMPOSE_FILE up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    sleep 10
    
    # Check service health
    if docker-compose -f $COMPOSE_FILE ps | grep -q "Up"; then
        log_info "Services started successfully"
    else
        log_error "Some services failed to start"
        docker-compose -f $COMPOSE_FILE logs
        exit 1
    fi
}

# Run health checks
health_check() {
    log_info "Running health checks..."
    
    # Wait for application to be ready
    for i in {1..30}; do
        if curl -f http://localhost:8000/health > /dev/null 2>&1; then
            log_info "Health check passed"
            return 0
        fi
        log_info "Waiting for application to be ready... ($i/30)"
        sleep 2
    done
    
    log_error "Health check failed"
    return 1
}

# Rollback function
rollback() {
    log_warn "Rolling back deployment..."
    
    if [ "$ENVIRONMENT" = "production" ]; then
        COMPOSE_FILE="docker-compose.prod.yml"
    else
        COMPOSE_FILE="docker-compose.yml"
    fi
    
    docker-compose -f $COMPOSE_FILE down
    
    # Restore previous version if available
    if docker images | grep -q "$SERVICE_NAME:previous"; then
        docker tag $SERVICE_NAME:previous $SERVICE_NAME:latest
        docker-compose -f $COMPOSE_FILE up -d
        log_info "Rollback completed"
    else
        log_error "No previous version available for rollback"
    fi
}

# Main deployment function
main() {
    log_info "Starting deployment for $ENVIRONMENT environment..."
    
    # Tag current version as previous for rollback
    if docker images | grep -q "$SERVICE_NAME:latest"; then
        docker tag $SERVICE_NAME:latest $SERVICE_NAME:previous
    fi
    
    check_prerequisites
    build_image
    
    if [ "$ENVIRONMENT" = "production" ]; then
        push_image
    fi
    
    deploy_compose
    
    if ! health_check; then
        log_error "Deployment failed health checks"
        rollback
        exit 1
    fi
    
    log_info "Deployment completed successfully!"
}

# Handle script arguments
case "${1:-}" in
    "development"|"dev")
        ENVIRONMENT="development"
        ;;
    "production"|"prod")
        ENVIRONMENT="production"
        ;;
    "rollback")
        rollback
        exit 0
        ;;
    "health")
        health_check
        exit $?
        ;;
    *)
        echo "Usage: $0 {development|production|rollback|health}"
        echo ""
        echo "Environment variables:"
        echo "  DOCKER_REGISTRY - Docker registry URL"
        echo "  IMAGE_TAG       - Image tag (default: latest)"
        echo ""
        exit 1
        ;;
esac

# Run main function
main