#!/bin/bash
echo "📺 Setting up Sonarr..."
mkdir -p ~/persistent/sonarr/config
chmod 700 ~/persistent/sonarr/config
# Ensure media directories exist
mkdir -p ~/media/tv
echo "✅ Sonarr setup complete"