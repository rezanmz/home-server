#!/bin/bash
set -e
echo "🤖 Setting up Hermes Agent..."

# Create persistent data directory
mkdir -p ~/persistent/hermes/data
mkdir -p ~/persistent/hermes/webui-data

# Hermes container runs as root by default
chmod 755 ~/persistent/hermes/data
chmod 755 ~/persistent/hermes/webui-data

# Clone Hermes agent from github so WebUI can mount its Python files
if [ ! -d ~/persistent/hermes/agent-source/.git ]; then
  echo "📥 Cloning Hermes agent source code..."
  rm -rf ~/persistent/hermes/agent-source
  git clone -b v2026.4.3 https://github.com/NousResearch/hermes-agent.git ~/persistent/hermes/agent-source
else
  echo "📥 Updating Hermes agent source code..."
  cd ~/persistent/hermes/agent-source
  git fetch
  git checkout v2026.4.3
  cd -
fi

# Build both images from source for ARM64
# (the official hermes-agent image only publishes amd64 builds)
echo "🔨 Building images from source (this may take a while on first run)..."
docker compose -p hermes build

echo "✅ Hermes Agent setup complete"
