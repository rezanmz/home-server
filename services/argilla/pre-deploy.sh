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

for dir in "$BASE_DIR/data" "$BASE_DIR/postgres" "$BASE_DIR/elasticsearch" "$BASE_DIR/redis"; do
  if [ -O "$dir" ]; then
    chmod 700 "$dir"
  else
    echo "ℹ️  Leaving permissions unchanged for $dir because it is owned by another user."
  fi
done

echo "✅ Argilla setup complete"
