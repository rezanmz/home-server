#!/bin/bash
echo "📋 Setting up LibreChat..."

# Define base persistent directory
BASE_DIR=~/persistent/librechat

# Create sub-directories
mkdir -p "$BASE_DIR/data-node"
mkdir -p "$BASE_DIR/images"
mkdir -p "$BASE_DIR/uploads"
mkdir -p "$BASE_DIR/logs"
mkdir -p "$BASE_DIR/meili_data_v1.35.1"
mkdir -p "$BASE_DIR/pgdata2"

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

if [ ! -f "$BASE_DIR/librechat.yaml" ]; then
  touch "$BASE_DIR/librechat.yaml"
fi

# Set permissions
# LibreChat generally runs as UID 1000, wait, it runs as `node` which is 1000 in standard NodeJS images.
# Let's set everything to 1000 to be safe for the app.
chown -R 1000:1000 "$BASE_DIR/images" "$BASE_DIR/uploads" "$BASE_DIR/logs"
chown 1000:1000 "$BASE_DIR/.env" "$BASE_DIR/librechat.yaml"

# MongoDB runs as 999
chown -R 999:999 "$BASE_DIR/data-node"

# Postgres (vectordb) runs as Postgres (999 or 70 depending on image) 
# usually pgvector user is 999 or Postgres user 999. Let's make it 700 to user. Wait, Pi Pi docker pg runs as 999 or root. Let's just permisson it wide open locally for initialization or default 999.
chown -R 999:999 "$BASE_DIR/pgdata2"

chmod 700 "$BASE_DIR/data-node" "$BASE_DIR/pgdata2" "$BASE_DIR/meili_data_v1.35.1"
chmod 600 "$BASE_DIR/.env" "$BASE_DIR/librechat.yaml"

echo "✅ LibreChat setup complete"
