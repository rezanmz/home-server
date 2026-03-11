#!/bin/bash
echo "🏠 Setting up Heimdall..."

# Create config directory
mkdir -p ~/persistent/heimdall/config

# Set permissions
chmod -R 700 ~/persistent/heimdall

echo "✅ Heimdall setup complete"