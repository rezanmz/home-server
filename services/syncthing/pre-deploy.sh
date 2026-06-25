#!/bin/bash
set -euo pipefail

# Pre-deploy script for Syncthing
# This script runs before the Docker containers are started

echo "Running pre-deploy script for Syncthing..."

# Create necessary directories
echo "Creating data directories if they don't exist..."
mkdir -p ~/persistent/syncthing/config
mkdir -p ~/persistent/syncthing/data

# Set proper permissions (PUID/PGID = 1000)
echo "Setting permissions on data directories..."
chown -R 1000:1000 ~/persistent/syncthing 2>/dev/null || {
  echo "⚠️ chown failed, setting permissive mode instead..."
  chmod -R 755 ~/persistent/syncthing
}

echo "✅ Pre-deploy script for Syncthing completed successfully"
