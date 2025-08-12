#!/bin/bash

# Development environment setup script
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Create development environment
setup_dev_env() {
    log_info "Setting up development environment..."
    
    # Create local cache directory
    mkdir -p ./dev_cache
    mkdir -p ./logs
    
    # Copy development config if it doesn't exist
    if [ ! -f "config/local.yaml" ]; then
        log_info "Creating local configuration..."
        cp config/development.yaml config/local.yaml
    fi
    
    # Set up environment variables
    if [ ! -f ".env" ]; then
        log_info "Creating .env file..."
        cat > .env << EOF
# Development Environment Variables
AGENT_CONFIG_PATH=config/local.yaml
AWS_REGION=us-east-1
OPENSEARCH_ENDPOINT=http://localhost:9200
CACHE_DIRECTORY=./dev_cache
LOG_LEVEL=DEBUG
AUTH_ENABLED=false
EOF
    fi
    
    log_info "Development environment setup complete"
}

# Install Python dependencies
install_dependencies() {
    log_info "Installing Python dependencies..."
    
    if command -v python3 &> /dev/null; then
        python3 -m pip install -r requirements.txt
    elif command -v python &> /dev/null; then
        python -m pip install -r requirements.txt
    else
        log_warn "Python not found, skipping dependency installation"
    fi
}

# Start development services
start_services() {
    log_info "Starting development services..."
    
    # Start supporting services only
    docker-compose up -d opensearch redis
    
    log_info "Waiting for services to be ready..."
    sleep 10
    
    # Check if OpenSearch is ready
    for i in {1..30}; do
        if curl -f http://localhost:9200 > /dev/null 2>&1; then
            log_info "OpenSearch is ready"
            break
        fi
        log_info "Waiting for OpenSearch... ($i/30)"
        sleep 2
    done
    
    log_info "Development services started"
    log_info "You can now run: python -m uvicorn agent_core.main:app --reload"
}

# Stop development services
stop_services() {
    log_info "Stopping development services..."
    docker-compose down
    log_info "Development services stopped"
}

# Clean up development environment
cleanup() {
    log_info "Cleaning up development environment..."
    
    # Stop services
    docker-compose down -v
    
    # Remove cache and logs
    rm -rf ./dev_cache
    rm -rf ./logs
    
    # Remove local config
    rm -f config/local.yaml
    rm -f .env
    
    log_info "Development environment cleaned up"
}

# Main function
case "${1:-setup}" in
    "setup")
        setup_dev_env
        install_dependencies
        ;;
    "start")
        start_services
        ;;
    "stop")
        stop_services
        ;;
    "cleanup")
        cleanup
        ;;
    *)
        echo "Usage: $0 {setup|start|stop|cleanup}"
        echo ""
        echo "Commands:"
        echo "  setup   - Set up development environment"
        echo "  start   - Start development services"
        echo "  stop    - Stop development services"
        echo "  cleanup - Clean up development environment"
        echo ""
        exit 1
        ;;
esac