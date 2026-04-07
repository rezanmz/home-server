#!/bin/bash
echo "📋 Setting up LibreChat..."

# Define base persistent directory
BASE_DIR=~/persistent/librechat

# Create sub-directories
mkdir -p "$BASE_DIR/images"
mkdir -p "$BASE_DIR/uploads"
mkdir -p "$BASE_DIR/logs"

# Ensure .env and librechat.yaml exist
if [ ! -f "$BASE_DIR/.env" ]; then
  cat <<EOF > "$BASE_DIR/.env"
# LibreChat Environment Setup
HOST=0.0.0.0
PORT=3080

# MongoDB
MONGO_URI=mongodb://librechat-mongodb:27017/LibreChat

# Search (Meilisearch)
SEARCH=true
MEILI_HOST=http://librechat-meilisearch:7700
MEILI_MASTER_KEY=LCSearchMasterKeyHSHS

# RAG
RAG_PORT=8000
RAG_API_URL=http://librechat-rag_api:8000

# General
DOMAIN_CLIENT=http://localhost:3080
DOMAIN_SERVER=http://localhost:3080

# Logging
DEBUG_LOGGING=true
EOF
fi

# Ensure cryptographic keys exist in .env
if ! grep -q "CREDS_KEY=" "$BASE_DIR/.env"; then
  cat <<EOF >> "$BASE_DIR/.env"

# Cryptographic Keys (Auto-generated)
CREDS_KEY=$(openssl rand -hex 16)
CREDS_IV=$(openssl rand -hex 8)
JWT_SECRET=$(openssl rand -hex 32)
JWT_REFRESH_SECRET=$(openssl rand -hex 32)
EOF
fi

if [ ! -f "$BASE_DIR/librechat.yaml" ]; then
  touch "$BASE_DIR/librechat.yaml"
fi

# Set permissions
# LibreChat generally runs as UID 1000, wait, it runs as `node` which is 1000 in standard NodeJS images.
# Let's set everything to 1000 to be safe for the app.
chown -R 1000:1000 "$BASE_DIR/images" "$BASE_DIR/uploads" "$BASE_DIR/logs"
chown 1000:1000 "$BASE_DIR/.env" "$BASE_DIR/librechat.yaml"

chmod 600 "$BASE_DIR/.env" "$BASE_DIR/librechat.yaml"

echo "✅ LibreChat setup complete"
