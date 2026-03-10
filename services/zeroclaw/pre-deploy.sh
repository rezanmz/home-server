#!/bin/bash
echo "🤖 Setting up ZeroClaw..."

# Create persistent data directory
mkdir -p ~/persistent/zeroclaw-data

# Set proper permissions
chmod 755 ~/persistent/zeroclaw-data

echo "📦 Fetching the latest edge repository..."
if [ ! -d "./zeroclaw-repo" ]; then
  git clone https://github.com/zeroclaw-labs/zeroclaw.git ./zeroclaw-repo
else
  cd ./zeroclaw-repo
  git pull origin master
  cd ..
fi

echo "🏗️ Building frontend assets using an ephemeral Node container..."
# This mounts the cloned web directory and compiles the UI into web/dist
docker run --rm -v $(pwd)/zeroclaw-repo/web:/app -w /app node:20-slim bash -c "npm install && npm run build"

echo "✅ ZeroClaw setup complete"