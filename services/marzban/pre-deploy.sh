#!/bin/bash
echo "🛡️ Setting up Marzban..."

# Create directory for database and certs
mkdir -p ~/persistent/marzban

# Permission check (Marzban runs as root inside the container usually)
# We ensure the host path is accessible
chmod 755 ~/persistent/marzban

echo "✅ Marzban setup complete"