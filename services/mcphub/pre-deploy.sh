#!/bin/bash
echo "📋 Setting up MCPHub..."

# Define base persistent directory
BASE_DIR=~/persistent/mcphub

# Create sub-directories and files
mkdir -p "$BASE_DIR/data"

if [ ! -f "$BASE_DIR/.env" ]; then
  echo "ADMIN_PASSWORD=strongadminpassword123" > "$BASE_DIR/.env"
fi

touch "$BASE_DIR/mcp_settings.json"

# Initialize mcp_settings.json if empty
if [ ! -s "$BASE_DIR/mcp_settings.json" ]; then
  echo '{ "mcpServers": {} }' > "$BASE_DIR/mcp_settings.json"
fi

# Set permissions
chown -R 1000:1000 "$BASE_DIR/data"
chown 1000:1000 "$BASE_DIR/.env" "$BASE_DIR/mcp_settings.json"

chmod 700 "$BASE_DIR/data"
chmod 600 "$BASE_DIR/.env"
chmod 644 "$BASE_DIR/mcp_settings.json"

echo "✅ MCPHub setup complete"
