#!/bin/bash
set -euo pipefail

# Pre-deploy script for Calibre-Web
# This script runs before the Docker containers are started

echo "📚 Setting up Calibre-Web..."

# Create necessary directories
echo "📁 Creating data directories if they don't exist..."
mkdir -p ~/persistent/calibre-web/config
mkdir -p ~/persistent/calibre-web/ingest
mkdir -p ~/persistent/shelfmark/config
mkdir -p ~/media/books

# Set proper permissions (PUID/PGID = 1000)
echo "🔒 Setting permissions on data directories..."
chown -R 1000:1000 ~/persistent/calibre-web 2>/dev/null || {
  echo "⚠️ chown failed, setting permissive mode instead..."
  chmod -R 755 ~/persistent/calibre-web 2>/dev/null || true
}

chown -R 1000:1000 ~/persistent/shelfmark 2>/dev/null || {
  echo "⚠️ chown failed, setting permissive mode instead..."
  chmod -R 755 ~/persistent/shelfmark 2>/dev/null || true
}

chmod 755 ~/media/books

echo "✅ Pre-deploy script for Calibre-Web completed successfully"
