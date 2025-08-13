#!/bin/bash
# Local Docker Services Manager
# This script mirrors the GitHub Actions workflow for local development and testing

set -e

# Configuration
SERVICES_DIR="services"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
STATE_FILE="$HOME/.docker_services_state"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Create logs directory
mkdir -p "$LOG_DIR"

# Function to discover services
discover_services() {
    log_info "Discovering services in $SERVICES_DIR directory..."
    
    local services=""
    if [ -d "$SERVICES_DIR" ]; then
        for service_dir in $SERVICES_DIR/*/; do
            if [ -f "${service_dir}docker-compose.yml" ] || [ -f "${service_dir}docker-compose.yaml" ]; then
                service_name=$(basename "$service_dir")
                services="$services$service_name "
                log_info "Found service: $service_name"
            fi
        done
    fi
    
    # Remove trailing space
    services=$(echo "$services" | sed 's/[[:space:]]*$//')
    echo "$services"
}

# Function to validate service configuration
validate_service() {
    local service=$1
    local service_dir="$SERVICES_DIR/$service"
    
    log_info "Validating configuration for $service..."
    
    local compose_file=""
    if [ -f "$service_dir/docker-compose.yml" ]; then
        compose_file="$service_dir/docker-compose.yml"
    elif [ -f "$service_dir/docker-compose.yaml" ]; then
        compose_file="$service_dir/docker-compose.yaml"
    else
        log_error "No docker-compose file found for $service"
        return 1
    fi
    
    if docker-compose -f "$compose_file" config > /dev/null 2>&1; then
        log_success "Configuration valid for $service"
        return 0
    else
        log_error "Invalid configuration for $service"
        return 1
    fi
}

# Function to deploy a service
deploy_service() {
    local service=$1
    local service_dir="$SERVICES_DIR/$service"
    local original_dir=$(pwd)
    
    log_info "Deploying service: $service"
    
    local compose_file=""
    if [ -f "$service_dir/docker-compose.yml" ]; then
        compose_file="docker-compose.yml"
    elif [ -f "$service_dir/docker-compose.yaml" ]; then
        compose_file="docker-compose.yaml"
    else
        log_error "No docker-compose file found for $service"
        return 1
    fi
    
    cd "$service_dir"
    
    # Pull images if possible
    if docker-compose -f "$compose_file" pull 2>/dev/null; then
        log_info "Images pulled for $service"
    else
        log_warning "Could not pull images for $service (might be building from source)"
    fi
    
    # Deploy the service
    if docker-compose -f "$compose_file" up -d --remove-orphans --force-recreate; then
        log_success "Service $service deployed successfully"
        
        # Wait and check status
        sleep 3
        if docker-compose -f "$compose_file" ps | grep -q "Up\|running"; then
            log_success "Service $service is running"
        else
            log_warning "Service $service may not be running properly"
            docker-compose -f "$compose_file" logs --tail=10
        fi
        
        cd "$original_dir"
        return 0
    else
        log_error "Failed to deploy service $service"
        docker-compose -f "$compose_file" logs --tail=20
        cd "$original_dir"
        return 1
    fi
}

# Function to remove a service
remove_service() {
    local service=$1
    
    log_info "Removing service: $service"
    
    # Find and stop containers
    local containers=$(docker ps -a --filter "name=${service}" --format "{{.Names}}" 2>/dev/null || true)
    if [ ! -z "$containers" ]; then
        log_info "Stopping and removing containers for $service..."
        echo "$containers" | xargs -r docker stop 2>/dev/null || true
        echo "$containers" | xargs -r docker rm 2>/dev/null || true
    fi
    
    # Remove networks
    local networks=$(docker network ls --filter "name=${service}" --format "{{.Name}}" | grep -v -E "bridge|host|none" 2>/dev/null || true)
    if [ ! -z "$networks" ]; then
        log_info "Removing networks for $service..."
        echo "$networks" | xargs -r docker network rm 2>/dev/null || true
    fi
    
    # Remove images
    local images=$(docker images --filter "reference=*${service}*" --format "{{.Repository}}:{{.Tag}}" 2>/dev/null || true)
    if [ ! -z "$images" ]; then
        log_info "Removing images for $service..."
        echo "$images" | xargs -r docker rmi --force 2>/dev/null || true
    fi
    
    log_success "Service $service removed"
}

# Function to check service status
check_service_status() {
    local service=$1
    local service_dir="$SERVICES_DIR/$service"
    local original_dir=$(pwd)
    
    local compose_file=""
    if [ -f "$service_dir/docker-compose.yml" ]; then
        compose_file="docker-compose.yml"
    elif [ -f "$service_dir/docker-compose.yaml" ]; then
        compose_file="docker-compose.yaml"
    else
        log_error "No docker-compose file found for $service"
        return 1
    fi
    
    cd "$service_dir"
    
    echo "📊 Status for $service:"
    docker-compose -f "$compose_file" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No containers found"
    
    cd "$original_dir"
}

# Function to show logs
show_service_logs() {
    local service=$1
    local lines=${2:-50}
    local service_dir="$SERVICES_DIR/$service"
    local original_dir=$(pwd)
    
    local compose_file=""
    if [ -f "$service_dir/docker-compose.yml" ]; then
        compose_file="docker-compose.yml"
    elif [ -f "$service_dir/docker-compose.yaml" ]; then
        compose_file="docker-compose.yaml"
    else
        log_error "No docker-compose file found for $service"
        return 1
    fi
    
    cd "$service_dir"
    
    echo "📜 Last $lines lines of logs for $service:"
    docker-compose -f "$compose_file" logs --tail="$lines"
    
    cd "$original_dir"
}

# Function to cleanup Docker resources
cleanup_docker() {
    log_info "Cleaning up Docker resources..."
    
    # Remove unused images
    docker image prune -f --filter "until=24h" 2>/dev/null || true
    
    # Remove unused networks
    docker network prune -f 2>/dev/null || true
    
    # Remove unused build cache
    docker builder prune -f --keep-storage 1GB 2>/dev/null || true
    
    log_success "Docker cleanup completed"
}

# Main deployment function
deploy_all() {
    log_info "🚀 Starting deployment of all services..."
    
    local current_services=$(discover_services)
    local previous_services=""
    
    # Load previous state
    if [ -f "$STATE_FILE" ]; then
        previous_services=$(cat "$STATE_FILE" | tr '\n' ' ' | sed 's/[[:space:]]*$//')
        log_info "Previously deployed: $previous_services"
    fi
    
    # Convert to arrays
    local current_array=($current_services)
    local previous_array=($previous_services)
    
    # Find removed services
    local removed_services=""
    for service in ${previous_array[@]}; do
        if [[ ! " ${current_array[@]} " =~ " $service " ]]; then
            removed_services="$removed_services$service "
        fi
    done
    removed_services=$(echo "$removed_services" | sed 's/[[:space:]]*$//')
    
    # Remove deleted services
    if [ ! -z "$removed_services" ]; then
        log_info "🗑️ Removing deleted services: $removed_services"
        for service in $removed_services; do
            remove_service "$service"
        done
    fi
    
    # Validate all current services
    local failed_validation=""
    for service in $current_services; do
        if ! validate_service "$service"; then
            failed_validation="$failed_validation$service "
        fi
    done
    
    if [ ! -z "$failed_validation" ]; then
        log_error "Validation failed for services: $failed_validation"
        exit 1
    fi
    
    # Deploy all current services
    local failed_deployments=""
    local successful_deployments=""
    
    for service in $current_services; do
        if deploy_service "$service"; then
            successful_deployments="$successful_deployments$service "
        else
            failed_deployments="$failed_deployments$service "
        fi
    done
    
    # Update state file
    echo "$current_services" | tr ' ' '\n' > "$STATE_FILE"
    
    # Summary
    echo ""
    log_info "📊 Deployment Summary"
    echo "===================="
    echo "✅ Successful: $successful_deployments"
    echo "❌ Failed: $failed_deployments"
    echo "🗑️ Removed: $removed_services"
    
    if [ ! -z "$failed_deployments" ]; then
        log_error "Some deployments failed!"
        exit 1
    else
        log_success "All deployments completed successfully!"
    fi
}

# Help function
show_help() {
    echo "Docker Services Manager"
    echo "======================"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  deploy                Deploy all services"
    echo "  deploy <service>      Deploy specific service"
    echo "  remove <service>      Remove specific service"
    echo "  status [service]      Show status of all services or specific service"
    echo "  logs <service> [lines] Show logs for service (default: 50 lines)"
    echo "  validate [service]    Validate all services or specific service"
    echo "  cleanup               Cleanup unused Docker resources"
    echo "  list                  List all discovered services"
    echo "  help                  Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 deploy             # Deploy all services"
    echo "  $0 deploy myservice   # Deploy only 'myservice'"
    echo "  $0 status             # Show status of all services"
    echo "  $0 logs myservice 100 # Show last 100 lines of logs for 'myservice'"
    echo "  $0 remove myservice   # Remove 'myservice'"
}

# Main script logic
case "${1:-help}" in
    "deploy")
        if [ -z "$2" ]; then
            deploy_all
        else
            validate_service "$2" && deploy_service "$2"
        fi
        ;;
    "remove")
        if [ -z "$2" ]; then
            log_error "Please specify a service to remove"
            exit 1
        fi
        remove_service "$2"
        ;;
    "status")
        if [ -z "$2" ]; then
            services=$(discover_services)
            for service in $services; do
                check_service_status "$service"
                echo ""
            done
        else
            check_service_status "$2"
        fi
        ;;
    "logs")
        if [ -z "$2" ]; then
            log_error "Please specify a service"
            exit 1
        fi
        show_service_logs "$2" "${3:-50}"
        ;;
    "validate")
        if [ -z "$2" ]; then
            services=$(discover_services)
            for service in $services; do
                validate_service "$service"
            done
        else
            validate_service "$2"
        fi
        ;;
    "cleanup")
        cleanup_docker
        ;;
    "list")
        services=$(discover_services)
        log_info "Discovered services:"
        for service in $services; do
            echo "  - $service"
        done
        ;;
    "help"|*)
        show_help
        ;;
esac