#!/bin/bash
echo "⬇️  Setting up Downloads service..."

# Create persistent config directories
mkdir -p ~/persistent/gluetun
mkdir -p ~/persistent/qbittorrent/config

# Set permissions
chmod 755 ~/persistent/gluetun
chmod 755 ~/persistent/qbittorrent/config

# Ensure the shared media directory exists (defined in samba/jellyfin)
mkdir -p ~/media/downloads
chmod 755 ~/media/downloads

echo "✅ Downloads setup completed!"