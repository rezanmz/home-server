#!/bin/bash
echo "🏠 Setting up Homepage..."

# Create config directory
mkdir -p ~/persistent/homepage/config

# Create default config files if they don't exist
# This ensures the container doesn't crash on first start
touch ~/persistent/homepage/config/settings.yaml
touch ~/persistent/homepage/config/services.yaml
touch ~/persistent/homepage/config/widgets.yaml
touch ~/persistent/homepage/config/bookmarks.yaml

# Set permissions
chmod -R 755 ~/persistent/homepage

echo "✅ Homepage setup complete"