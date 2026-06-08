#!/bin/bash
set -euo pipefail

echo "🔐 Setting up Authentik..."

required_vars=(
  AUTHENTIK_SECRET_KEY
  AUTHENTIK_POSTGRES_PASSWORD
  AUTHENTIK_BOOTSTRAP_PASSWORD_HASH
)

for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "❌ $var must be set as a GitHub Actions secret."
    exit 1
  fi
done

if [ ${#AUTHENTIK_POSTGRES_PASSWORD} -gt 99 ]; then
  echo "❌ AUTHENTIK_POSTGRES_PASSWORD must be 99 characters or fewer for PostgreSQL."
  exit 1
fi

if [ ${#AUTHENTIK_SECRET_KEY} -lt 50 ]; then
  echo "❌ AUTHENTIK_SECRET_KEY should be a long random secret."
  exit 1
fi

BASE_DIR=~/persistent/authentik

mkdir -p "$BASE_DIR/data"
mkdir -p "$BASE_DIR/certs"
mkdir -p "$BASE_DIR/custom-templates"
mkdir -p "$BASE_DIR/postgres"

for dir in "$BASE_DIR/data" "$BASE_DIR/certs" "$BASE_DIR/custom-templates" "$BASE_DIR/postgres"; do
  if [ -O "$dir" ]; then
    chmod 700 "$dir"
  else
    echo "ℹ️  Leaving permissions unchanged for $dir because it is owned by another user."
  fi
done

echo "✅ Authentik setup complete"
