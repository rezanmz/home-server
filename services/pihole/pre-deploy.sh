#!/bin/bash
echo "🛡️ Setting up Pi-hole..."

# Create config directories
mkdir -p ~/persistent/pihole/etc-pihole
mkdir -p ~/persistent/pihole/etc-dnsmasq.d

# # Fix Port 53 Conflict (Ubuntu/Debian/Raspbian specific)
# # We need to stop systemd-resolved from hogging port 53
# if systemctl is-active --quiet systemd-resolved; then
#     echo "⚠️  Disabling systemd-resolved stub listener to free port 53..."
#     # Determine the location of the config file
#     if [ -f /etc/systemd/resolved.conf ]; then
#         # Uncomment/Change DNSStubListener=yes to no
#         sudo sed -i 's/#DNSStubListener=yes/DNSStubListener=no/' /etc/systemd/resolved.conf
#         sudo sed -i 's/DNSStubListener=yes/DNSStubListener=no/' /etc/systemd/resolved.conf
        
#         # Restart the service to apply changes
#         sudo systemctl restart systemd-resolved
#         echo "✅ systemd-resolved updated"
#     fi
# fi

echo "✅ Pi-hole setup complete"