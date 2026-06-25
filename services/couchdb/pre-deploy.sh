#!/bin/bash
set -euo pipefail

# Pre-deploy script for CouchDB (Obsidian LiveSync)
# This script runs before the Docker containers are started

echo "Running pre-deploy script for CouchDB..."

if [ -z "${COUCHDB_USER:-}" ]; then
  echo "❌ COUCHDB_USER must be set as a GitHub Actions secret."
  exit 1
fi

if [ -z "${COUCHDB_PASSWORD:-}" ]; then
  echo "❌ COUCHDB_PASSWORD must be set as a GitHub Actions secret."
  exit 1
fi

# Create necessary directories
echo "Creating data directories if they don't exist..."
mkdir -p ~/persistent/couchdb/data
mkdir -p ~/persistent/couchdb/etc

# Copy local.ini BEFORE chown (runner still owns the dirs at this point)
echo "Copying CouchDB configuration..."
cp -f ./config/local.ini ~/persistent/couchdb/etc/local.ini

# Set proper permissions (CouchDB runs as UID 5984 inside the container)
echo "Setting permissions on data directories..."
sudo chown -R 5984:5984 ~/persistent/couchdb/data ~/persistent/couchdb/etc 2>/dev/null || {
  echo "⚠️ chown failed (no sudo), setting permissive mode instead..."
  chmod -R 777 ~/persistent/couchdb/data ~/persistent/couchdb/etc
}

echo "✅ Pre-deploy script for CouchDB completed successfully"
