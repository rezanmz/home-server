#!/bin/bash
set -euo pipefail

# Pre-deploy script for Actual Budget service
# This script runs before the Docker containers are started

echo "Running pre-deploy script for Actual Budget..."

if [ -z "${ACTUAL_OPENID_CLIENT_ID:-}" ]; then
  echo "❌ ACTUAL_OPENID_CLIENT_ID must be set as a GitHub Actions secret."
  exit 1
fi

if [ -z "${ACTUAL_OPENID_CLIENT_SECRET:-}" ]; then
  echo "❌ ACTUAL_OPENID_CLIENT_SECRET must be set as a GitHub Actions secret."
  exit 1
fi

# Create necessary directories
echo "Creating data directories if they don't exist..."
mkdir -p ~/persistent/actual-budget

# Set proper permissions
echo "Setting permissions on data directories..."
chmod 700 ~/persistent/actual-budget

echo "✅ Pre-deploy script for Actual Budget completed successfully"
