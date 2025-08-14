#!/bin/bash

# Pre-deploy script for Actual Budget service
# This script runs before the Docker containers are started

echo "Running pre-deploy script for Actual Budget..."

# Create necessary directories
echo "Creating data directories if they don't exist..."
mkdir -p ~/persistent/actual-budget

# Set proper permissions
echo "Setting permissions on data directories..."
chmod 755 ~/persistent/actual-budget

echo "✅ Pre-deploy script for Actual Budget completed successfully"
