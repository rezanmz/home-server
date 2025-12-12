#!/bin/bash
echo "🛡️ Setting up Marzban..."

# Create main directory
mkdir -p ~/persistent/marzban/certs

# Generate Self-Signed Certificates if they don't exist
if [ ! -f ~/persistent/marzban/certs/key.pem ]; then
    echo "🔐 Generating self-signed SSL for internal communication..."
    openssl req -x509 -newkey rsa:4096 -keyout ~/persistent/marzban/certs/key.pem -out ~/persistent/marzban/certs/fullchain.pem -days 3650 -nodes -subj "/CN=marzban-internal"
fi

# Set permissions
chmod 755 ~/persistent/marzban
chmod -R 644 ~/persistent/marzban/certs
chmod 600 ~/persistent/marzban/certs/key.pem

echo "✅ Marzban setup complete"