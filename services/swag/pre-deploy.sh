#!/bin/bash
echo "🔒 Setting up SWAG..."

# 1. Create the persistent directories
mkdir -p ~/persistent/swag/config/nginx/proxy-confs

# 2. Copy subdomain configs from your Repo into the Persistent Volume
#    This forces the live server to match your Git repository.
echo "🔄 Syncing proxy configurations..."
cp -f ./config/nginx/proxy-confs/*.conf ~/persistent/swag/config/nginx/proxy-confs/

# 3. Set permissions (ensure the container user can read them)
chmod -R 755 ~/persistent/swag/config

echo "✅ SWAG setup complete"