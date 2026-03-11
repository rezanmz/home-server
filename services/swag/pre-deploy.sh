#!/bin/bash
echo "🔒 Setting up SWAG..."

# 1. Create the persistent directories
mkdir -p ~/persistent/swag/config/nginx/proxy-confs
mkdir -p ~/persistent/swag/config/dns-conf

# 2. Copy subdomain configs from your Repo into the Persistent Volume
#    This forces the live server to match your Git repository.
echo "🔄 Syncing proxy configurations..."
cp -f ./config/nginx/proxy-confs/*.conf ~/persistent/swag/config/nginx/proxy-confs/

# 3. Set permissions (ensure the container user can read them)
chmod -R 700 ~/persistent/swag/config

# 4. Create Cloudflare DNS validation credentials
if [ -n "$CLOUDFLARE_API_TOKEN" ]; then
    echo "🔑 Setting up Cloudflare DNS validation credentials..."
    echo "dns_cloudflare_api_token = $CLOUDFLARE_API_TOKEN" > ~/persistent/swag/config/dns-conf/cloudflare.ini
    chmod 600 ~/persistent/swag/config/dns-conf/cloudflare.ini
fi

echo "✅ SWAG setup complete"