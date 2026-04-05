#!/bin/bash
echo "📋 Setting up Vikunja..."

# Create persistent directories
mkdir -p ~/persistent/vikunja/files
mkdir -p ~/persistent/vikunja/db

# Vikunja runs as UID 1000 inside the container
chown -R 1000 ~/persistent/vikunja/files

# Set permissions
chmod 700 ~/persistent/vikunja/files
chmod 700 ~/persistent/vikunja/db

echo "✅ Vikunja setup complete"
