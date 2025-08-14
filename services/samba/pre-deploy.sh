#!/bin/bash

echo "🔧 Setting up Samba service..."

# Ensure media directories exist and are readable
if [ ! -d ~/media ]; then
    echo "⚠️  Warning: ~/media directory not found. Creating it..."
    mkdir -p ~/media/movies ~/media/tv
fi

if [ ! -d ~/media/movies ]; then
    echo "⚠️  Warning: ~/media/movies directory not found. Creating it..."
    mkdir -p ~/media/movies
fi

if [ ! -d ~/media/tv ]; then
    echo "⚠️  Warning: ~/media/tv directory not found. Creating it..."
    mkdir -p ~/media/tv
fi

# Check if directories are readable
if [ ! -r ~/media ]; then
    echo "❌ Error: ~/media directory is not readable"
    exit 1
fi

# Ensure avahi services directory exists for service discovery
if [ ! -d /etc/avahi/services ]; then
    echo "📡 Creating avahi services directory..."
    sudo mkdir -p /etc/avahi/services 2>/dev/null || {
        echo "⚠️  Warning: Could not create /etc/avahi/services directory. Service discovery may not work."
        echo "   This is normal if running without sudo privileges."
    }
fi

echo "✅ Samba service setup completed!"
echo ""
echo "📋 Service Details:"
echo "   - Server Name: HomeServer"
echo "   - Workgroup: WORKGROUP"
echo "   - Username: pi"
echo "   - Password: raspberry"
echo ""
echo "📁 Available Shares:"
echo "   - All Media: \\\\HomeServer\\Media"
echo ""
echo "🔒 Security Notes:"
echo "   - All shares are read-only for safety"
echo "   - Change the default password in docker-compose.yml"
echo "   - Consider setting up proper user accounts"
