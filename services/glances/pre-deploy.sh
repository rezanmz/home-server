#!/bin/bash
echo "📊 Setting up Glances..."

# Create config directory
mkdir -p ~/persistent/glances/config

# Set permissions
chmod -R 700 ~/persistent/glances

echo "✅ Glances setup complete"
