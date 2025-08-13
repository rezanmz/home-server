#!/bin/sh

set -e

echo "Setting up Cloudflare DNS for certificate management..."

# Create necessary directories
mkdir -p /etc/letsencrypt

# Create Cloudflare credentials file
printf 'dns_cloudflare_api_token = %s\n' "$CLOUDFLARE_API_TOKEN" > /etc/letsencrypt/cloudflare.ini
chmod 600 /etc/letsencrypt/cloudflare.ini

echo "Cloudflare credentials configured for domain: $DOMAIN"

# Check if certificate already exists
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "Certificate already exists for $DOMAIN, starting renewal loop..."
else
    echo "Issuing initial certificate for $DOMAIN..."
    
    # Set staging flag if needed
    EXTRA=""
    if [ "${LETSENCRYPT_STAGING:-false}" = "true" ]; then
        EXTRA="--test-cert"
        echo "Using Let's Encrypt staging environment"
    fi
    
    # Issue the certificate
    certbot certonly \
        --dns-cloudflare \
        --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
        -d "$DOMAIN" \
        --agree-tos \
        --non-interactive \
        --email "$LETSENCRYPT_EMAIL" \
        --rsa-key-size 4096 \
        $EXTRA
    
    echo "Initial certificate issued successfully for $DOMAIN"
fi

# Start renewal loop
echo "Starting certificate renewal loop (checks every 12 hours)..."
while true; do
    EXTRA=""
    if [ "${LETSENCRYPT_STAGING:-false}" = "true" ]; then
        EXTRA="--test-cert"
    fi
    
    echo "Checking for certificate renewal..."
    certbot renew --quiet $EXTRA || {
        echo "Certificate renewal check failed, but continuing..."
    }
    
    echo "Next renewal check in 12 hours..."
    sleep 12h
done
