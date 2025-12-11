#!/bin/bash
echo "🎬 Setting up Radarr..."
mkdir -p ~/persistent/radarr/config
chmod 755 ~/persistent/radarr/config
# Ensure media directories exist (also handled by Samba/Jellyfin scripts)
mkdir -p ~/media/movies
echo "✅ Radarr setup complete"