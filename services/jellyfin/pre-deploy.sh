#!/bin/bash
echo "🎬 Setting up Jellyfin media server..."

# Create necessary directories for Jellyfin data
echo "📁 Creating Jellyfin directories..."
mkdir -p ~/persistent/jellyfin/config
mkdir -p ~/persistent/jellyfin/cache

# Set proper permissions (jellyfin runs as user 1000:1000)
echo "🔒 Setting permissions..."
chmod 755 ~/persistent/jellyfin/config
chmod 755 ~/persistent/jellyfin/cache

# Create example media directories (user can customize these)
echo "📺 Creating example media directories..."
mkdir -p ~/media/movies
mkdir -p ~/media/tv
mkdir -p ~/media/music

# Set read permissions for media directories
chmod 755 ~/media/movies
chmod 755 ~/media/tv
chmod 755 ~/media/music

echo "ℹ️  NOTE: Please update the following in docker-compose.yml:"
echo "   1. Change JELLYFIN_PublishedServerUrl to your Raspberry Pi's actual IP address"
echo "   2. Add your actual media directory paths to the volumes section"
echo "   3. Example media paths created at ~/media/ (movies, tv, music)"

echo "✅ Jellyfin pre-deploy setup completed!"
echo "🌐 After deployment, access Jellyfin at: http://YOUR_PI_IP:8096"
