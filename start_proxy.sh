#!/bin/bash
# Fill in values before running — never commit this file with real credentials

# Backend API (token auth)
BACKEND_API_TOKEN=your-api-token
BACKEND_API_AUTH_SCHEME=Token          # Token or Bearer
BACKEND_API_ENDPOINT=https://your.api.domain/
BACKEND_API_VERIFY_SSL=true            # set to false for self-signed certs

# Backend API (basic auth — uncomment to use instead of token)
# BACKEND_API_USER=username
# BACKEND_API_PASSWORD=mysecret

# Proxy settings
PROXY_TOKEN=choose-a-strong-secret-for-proxy-auth
PROXY_PORT=8888                        # optional, defaults to 8888

export BACKEND_API_TOKEN BACKEND_API_AUTH_SCHEME BACKEND_API_ENDPOINT
export BACKEND_API_VERIFY_SSL PROXY_TOKEN PROXY_PORT

python3 proxy.py
