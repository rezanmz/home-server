#!/bin/bash
echo "📋 Setting up Vikunja..."

# Create persistent directories
mkdir -p ~/persistent/vikunja/files
mkdir -p ~/persistent/vikunja/db

# Vikunja runs as UID 1000
chown -R 1000 ~/persistent/vikunja/files
chmod 700 ~/persistent/vikunja/files

# PostgreSQL runs as UID 999 inside the official image
chown -R 999:999 ~/persistent/vikunja/db
chmod 700 ~/persistent/vikunja/db

echo "✅ Vikunja setup complete"
