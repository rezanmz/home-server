#!/bin/bash
set -euo pipefail

echo "Setting up open-webui service directories..."

required_vars=(
  OPEN_WEBUI_SECRET_KEY
  OPEN_WEBUI_OAUTH_CLIENT_ID
  OPEN_WEBUI_OAUTH_CLIENT_SECRET
)

for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "❌ $var must be set as a GitHub Actions secret."
    exit 1
  fi
done

if [ ${#OPEN_WEBUI_SECRET_KEY} -lt 32 ]; then
  echo "❌ OPEN_WEBUI_SECRET_KEY should be at least 32 characters."
  exit 1
fi

# Create persistent storage directories
mkdir -p ~/persistent/open-webui/data

echo "open-webui pre-deploy step completed."
