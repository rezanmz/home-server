#!/bin/bash
set -euo pipefail

echo "📋 Setting up MCPHub..."

# Define base persistent directory
BASE_DIR=~/persistent/mcphub

if [ -z "${MCPHUB_ADMIN_PASSWORD:-}" ]; then
  echo "❌ MCPHUB_ADMIN_PASSWORD must be set as a GitHub Actions secret."
  exit 1
fi

if [ "$MCPHUB_ADMIN_PASSWORD" = "strongadminpassword123" ]; then
  echo "❌ MCPHUB_ADMIN_PASSWORD must not use the old generated default."
  exit 1
fi

if [ ${#MCPHUB_ADMIN_PASSWORD} -lt 16 ]; then
  echo "❌ MCPHUB_ADMIN_PASSWORD must be at least 16 characters."
  exit 1
fi

# Create sub-directories and files
mkdir -p "$BASE_DIR/data"

touch "$BASE_DIR/.env"

tmp_env=$(mktemp)
grep -v '^ADMIN_PASSWORD=' "$BASE_DIR/.env" > "$tmp_env" || true
printf 'ADMIN_PASSWORD=%s\n' "$MCPHUB_ADMIN_PASSWORD" >> "$tmp_env"
mv "$tmp_env" "$BASE_DIR/.env"

touch "$BASE_DIR/mcp_settings.json"

# Initialize mcp_settings.json if empty
if [ ! -s "$BASE_DIR/mcp_settings.json" ]; then
  echo '{ "mcpServers": {} }' > "$BASE_DIR/mcp_settings.json"
fi

# Set permissions without requiring the deploy runner to be root.
if [ -O "$BASE_DIR/data" ]; then
  chmod 700 "$BASE_DIR/data"
else
  echo "ℹ️  Leaving permissions unchanged for $BASE_DIR/data because it is owned by another user."
fi

if [ -O "$BASE_DIR/.env" ]; then
  chmod 600 "$BASE_DIR/.env"
else
  echo "ℹ️  Leaving permissions unchanged for $BASE_DIR/.env because it is owned by another user."
fi

if [ -O "$BASE_DIR/mcp_settings.json" ]; then
  chmod 644 "$BASE_DIR/mcp_settings.json"
else
  echo "ℹ️  Leaving permissions unchanged for $BASE_DIR/mcp_settings.json because it is owned by another user."
fi

echo "✅ MCPHub setup complete"
