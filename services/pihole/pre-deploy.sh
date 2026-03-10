#!/bin/bash
echo "🕳️ Setting up Pi-hole..."

# Create persistent directory for Pi-hole v6
mkdir -p ~/persistent/pihole/etc-pihole

# Set proper permissions
chmod 755 ~/persistent/pihole/etc-pihole

echo "✅ Pi-hole setup complete"