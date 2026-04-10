#!/bin/bash
set -e

echo "Setting up open-webui service directories..."

# Create persistent storage directories
mkdir -p ~/persistent/open-webui/data

echo "open-webui pre-deploy step completed."
