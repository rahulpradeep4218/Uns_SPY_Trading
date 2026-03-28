#!/bin/bash

# 1. Enable automatic export (so you don't need 'export' in the .env file)
set -a

# 2. Check if .env exists before sourcing to prevent a crash
if [ -f .env ]; then
    source .env
else
    echo "Error: .env file not found"
fi

echo "Scope: $OAUTH2_PROXY_SCOPE"

# 3. Disable automatic export
set +a