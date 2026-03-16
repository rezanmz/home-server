#!/bin/bash
echo "🔒 Setting up SWAG..."

# 1. Create the persistent directories
mkdir -p ~/persistent/swag/config/nginx/proxy-confs
mkdir -p ~/persistent/swag/config/dns-conf
mkdir -p ~/persistent/swag/config/www

# 2. Copy subdomain configs from your Repo into the Persistent Volume
#    This forces the live server to match your Git repository.
echo "🔄 Syncing proxy configurations..."
cp -f ./config/nginx/proxy-confs/*.conf ~/persistent/swag/config/nginx/proxy-confs/

# 3. Copy custom error pages (e.g. 403.html) so nginx error_page directives work
echo "🔄 Syncing custom error pages..."
cp -f ./config/www/403.html ~/persistent/swag/config/www/

# 3a. Inject quips.json into 403.html (replaces %%QUIPS_JSON%% placeholder)
#     This avoids a runtime fetch that would be blocked by nginx deny rules.
if [ -f ./config/www/quips.json ]; then
    echo "🎲 Injecting quips into 403 page..."
    python3 -c "
import json
html = open('$HOME/persistent/swag/config/www/403.html').read()
quips = open('./config/www/quips.json').read().strip()
html = html.replace('%%QUIPS_JSON%%', quips)
open('$HOME/persistent/swag/config/www/403.html', 'w').write(html)
"
fi

# 4. Set permissions (ensure the container user can read them)
chmod -R 700 ~/persistent/swag/config

# 5. Create Cloudflare DNS validation credentials
if [ -n "$CLOUDFLARE_API_TOKEN" ]; then
    echo "🔑 Setting up Cloudflare DNS validation credentials..."
    echo "dns_cloudflare_api_token = $CLOUDFLARE_API_TOKEN" > ~/persistent/swag/config/dns-conf/cloudflare.ini
    chmod 600 ~/persistent/swag/config/dns-conf/cloudflare.ini
fi

echo "✅ SWAG setup complete"