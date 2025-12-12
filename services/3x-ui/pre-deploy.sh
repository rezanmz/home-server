#!/bin/bash
echo "🛡️ Setting up 3x-ui..."

# Create persistent directories for database and custom certs
mkdir -p ~/persistent/3x-ui/db
mkdir -p ~/persistent/3x-ui/cert

# Set permissions
chmod 755 ~/persistent/3x-ui

echo "✅ 3x-ui setup complete"