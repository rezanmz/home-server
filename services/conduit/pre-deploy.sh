#!/bin/bash
echo "🌐 Setting up Conduit..."

# Create persistent directory for keys and state
mkdir -p ~/persistent/conduit/data

# Set permissions
chmod 755 ~/persistent/conduit/data

echo "✅ Conduit setup complete"
