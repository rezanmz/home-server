#!/bin/bash
set -euo pipefail

echo "🏷️  Setting up Argilla annotation service..."

if [ -z "${ARGILLA_PASSWORD:-}" ]; then
  echo "❌ ARGILLA_PASSWORD must be set as a GitHub Actions secret."
  exit 1
fi

if [ ${#ARGILLA_PASSWORD} -lt 8 ]; then
  echo "❌ ARGILLA_PASSWORD must be at least 8 characters."
  exit 1
fi

if [ -z "${ARGILLA_API_KEY:-}" ]; then
  echo "❌ ARGILLA_API_KEY must be set as a GitHub Actions secret."
  exit 1
fi

BASE_DIR=~/persistent/argilla

mkdir -p "$BASE_DIR/data"
mkdir -p "$BASE_DIR/postgres"
mkdir -p "$BASE_DIR/elasticsearch"
mkdir -p "$BASE_DIR/redis"

# Argilla server runs as UID/GID 1000 inside argilla/argilla-server.
chown -R 1000:1000 "$BASE_DIR/data"
chmod 700 "$BASE_DIR/data"

# PostgreSQL official image initializes as the postgres user.
chown -R 999:999 "$BASE_DIR/postgres"
chmod 700 "$BASE_DIR/postgres"

# Elasticsearch runs as uid 1000 and group 0.
chown -R 1000:0 "$BASE_DIR/elasticsearch"
chmod 775 "$BASE_DIR/elasticsearch"

chmod 700 "$BASE_DIR/redis"

echo "✅ Argilla setup complete"
