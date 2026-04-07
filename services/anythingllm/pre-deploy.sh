#!/bin/bash
echo "📋 Setting up AnythingLLM..."

# Create persistent directories
mkdir -p ~/persistent/anythingllm/storage
mkdir -p ~/persistent/anythingllm/db

# Ensure .env exists
touch ~/persistent/anythingllm/.env

# AnythingLLM runs as UID 1000
chown -R 1000 ~/persistent/anythingllm/storage
chown 1000 ~/persistent/anythingllm/.env
chmod 700 ~/persistent/anythingllm/storage
chmod 600 ~/persistent/anythingllm/.env

# PostgreSQL runs as UID 999 inside the official image
chown -R 999:999 ~/persistent/anythingllm/db
chmod 700 ~/persistent/anythingllm/db

echo "✅ AnythingLLM setup complete"
