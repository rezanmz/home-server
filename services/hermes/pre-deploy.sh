#!/bin/bash
echo "🤖 Setting up Hermes Agent..."

# Create persistent data directory
mkdir -p ~/persistent/hermes/data

# Hermes container runs as root by default
chmod 755 ~/persistent/hermes/data

# Clone hermes-agent source for the WebUI (it needs the Python modules)
if [ ! -d ~/persistent/hermes/agent-src ]; then
    echo "📥 Cloning hermes-agent source for WebUI..."
    git clone --branch v2026.4.3 --depth 1 https://github.com/NousResearch/hermes-agent.git ~/persistent/hermes/agent-src
else
    echo "✓ hermes-agent source already present"
fi

# Build the hermes-agent image from source for ARM64
# (the official image only publishes amd64 builds)
echo "🔨 Building hermes-agent image from source (this may take a while on first run)..."
docker compose -p hermes build hermes

echo "✅ Hermes Agent setup complete"
