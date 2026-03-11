#!/bin/bash
echo "💾 Setting up Duplicati..."

# Create config and backup directories
mkdir -p ~/persistent/duplicati/config
mkdir -p ~/persistent/duplicati/backups

# Set permissions
chmod 700 ~/persistent/duplicati/config
chmod 700 ~/persistent/duplicati/backups

echo "✅ Duplicati setup complete"
