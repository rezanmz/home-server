#!/bin/bash

# Home Server Management Script
# This script helps with local testing and management of services

set -e

SERVICES_DIR="services"

usage() {
    echo "Usage: $0 [command] [service_name]"
    echo ""
    echo "Commands:"
    echo "  list                    List all available services"
    echo "  start [service]         Start a specific service"
    echo "  stop [service]          Stop a specific service"
    echo "  restart [service]       Restart a specific service"
    echo "  logs [service]          Show logs for a specific service"
    echo "  status                  Show status of all services"
    echo "  start-all              Start all services"
    echo "  stop-all               Stop all services"
    echo "  validate [service]      Validate service configuration"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 start nginx"
    echo "  $0 stop nginx"
    echo "  $0 logs nginx"
    echo "  $0 status"
}

list_services() {
    echo "Available services:"
    if [ -d "$SERVICES_DIR" ]; then
        for service_dir in "$SERVICES_DIR"/*; do
            if [ -d "$service_dir" ]; then
                service_name=$(basename "$service_dir")
                echo "  - $service_name"
            fi
        done
    else
        echo "No services directory found."
    fi
}

validate_service() {
    local service_name="$1"
    local service_dir="$SERVICES_DIR/$service_name"
    
    if [ ! -d "$service_dir" ]; then
        echo "Error: Service '$service_name' not found in $SERVICES_DIR/"
        exit 1
    fi
    
    if [ ! -f "$service_dir/docker-compose.yml" ] && [ ! -f "$service_dir/docker-compose.yaml" ]; then
        echo "Error: No docker-compose file found in $service_dir"
        exit 1
    fi
    
    echo "Service '$service_name' configuration is valid"
    
    # Test docker-compose config
    cd "$service_dir"
    if docker compose config > /dev/null 2>&1; then
        echo "Docker Compose configuration is valid"
    else
        echo "Warning: Docker Compose configuration has issues"
        docker compose config
    fi
}

start_service() {
    local service_name="$1"
    local service_dir="$SERVICES_DIR/$service_name"
    
    validate_service "$service_name"
    
    echo "Starting service: $service_name"
    cd "$service_dir"
    docker compose -p "$service_name" up -d
    echo "Service '$service_name' started"
}

stop_service() {
    local service_name="$1"
    local service_dir="$SERVICES_DIR/$service_name"
    
    if [ ! -d "$service_dir" ]; then
        echo "Error: Service '$service_name' not found in $SERVICES_DIR/"
        exit 1
    fi
    
    echo "Stopping service: $service_name"
    cd "$service_dir"
    docker compose -p "$service_name" down
    echo "Service '$service_name' stopped"
}

restart_service() {
    stop_service "$1"
    sleep 2
    start_service "$1"
}

show_logs() {
    local service_name="$1"
    local service_dir="$SERVICES_DIR/$service_name"
    
    if [ ! -d "$service_dir" ]; then
        echo "Error: Service '$service_name' not found in $SERVICES_DIR/"
        exit 1
    fi
    
    cd "$service_dir"
    docker compose -p "$service_name" logs -f
}

show_status() {
    echo "=== Docker System Overview ==="
    docker system df
    echo ""
    
    echo "=== Running Containers ==="
    docker ps
    echo ""
    
    echo "=== Docker Compose Services ==="
    docker compose ls 2>/dev/null || echo "No compose services found"
    echo ""
    
    echo "=== Service Status ==="
    if [ -d "$SERVICES_DIR" ]; then
        for service_dir in "$SERVICES_DIR"/*; do
            if [ -d "$service_dir" ]; then
                service_name=$(basename "$service_dir")
                cd "$service_dir"
                echo "Service: $service_name"
                if docker compose -p "$service_name" ps --services --filter "status=running" | grep -q .; then
                    echo "  Status: ✅ Running"
                else
                    echo "  Status: ❌ Stopped"
                fi
                cd - > /dev/null
            fi
        done
    fi
}

start_all() {
    echo "Starting all services..."
    if [ -d "$SERVICES_DIR" ]; then
        for service_dir in "$SERVICES_DIR"/*; do
            if [ -d "$service_dir" ]; then
                service_name=$(basename "$service_dir")
                start_service "$service_name"
            fi
        done
    fi
    echo "All services started"
}

stop_all() {
    echo "Stopping all services..."
    if [ -d "$SERVICES_DIR" ]; then
        for service_dir in "$SERVICES_DIR"/*; do
            if [ -d "$service_dir" ]; then
                service_name=$(basename "$service_dir")
                stop_service "$service_name"
            fi
        done
    fi
    echo "All services stopped"
}

# Main script logic
case "$1" in
    "list")
        list_services
        ;;
    "start")
        if [ -z "$2" ]; then
            echo "Error: Service name required"
            usage
            exit 1
        fi
        start_service "$2"
        ;;
    "stop")
        if [ -z "$2" ]; then
            echo "Error: Service name required"
            usage
            exit 1
        fi
        stop_service "$2"
        ;;
    "restart")
        if [ -z "$2" ]; then
            echo "Error: Service name required"
            usage
            exit 1
        fi
        restart_service "$2"
        ;;
    "logs")
        if [ -z "$2" ]; then
            echo "Error: Service name required"
            usage
            exit 1
        fi
        show_logs "$2"
        ;;
    "status")
        show_status
        ;;
    "start-all")
        start_all
        ;;
    "stop-all")
        stop_all
        ;;
    "validate")
        if [ -z "$2" ]; then
            echo "Error: Service name required"
            usage
            exit 1
        fi
        validate_service "$2"
        ;;
    *)
        usage
        exit 1
        ;;
esac
