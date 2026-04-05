#!/bin/bash
echo "🤖 Setting up Hermes Agent..."

# Create persistent data directory
mkdir -p ~/persistent/hermes/data

# Hermes container runs as root by default
chmod 755 ~/persistent/hermes/data

# Build the hermes-agent image from source for ARM64
# (the official image only publishes amd64 builds)
echo "🔨 Building hermes-agent image from source (this may take a while on first run)..."
docker compose -p hermes build hermes

echo "✅ Hermes Agent setup complete"
