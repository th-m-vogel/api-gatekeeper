#!/usr/bin/env python3
"""
API Gatekeeper
Allowlist-based proxy to a backend API.
Authenticates clients with PROXY_TOKEN, forwards permitted requests using
BACKEND_API_TOKEN (Token/Bearer auth) or BACKEND_API_USER/BACKEND_API_PASSWORD
(Basic auth).

Environment variables:
  PROXY_TOKEN              — token clients must present (Bearer)
  PROXY_PORT               — listening port (default: 8888)
  BACKEND_API_ENDPOINT     — base URL of the backend API
  BACKEND_API_TOKEN        — backend API token (mutually exclusive with basic auth)
  BACKEND_API_AUTH_SCHEME  — auth scheme for token: Token or Bearer (default: Token)
  BACKEND_API_USER         — backend API username (basic auth)
  BACKEND_API_PASSWORD     — backend API password (basic auth)
  BACKEND_API_VERIFY_SSL   — verify backend SSL certificate: true/false (default: true)
"""

import logging
import os
import re
import sys
from datetime import datetime, timezone

import requests
import yaml
from flask import Flask, jsonify, request, Response

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "proxy_config.yaml")

app = Flask(__name__)
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("api-gatekeeper")


def load_config() -> list[dict]:
    """Load and return allowed endpoints from config file."""
    with open(CONFIG_FILE) as f:
        data = yaml.safe_load(f)
    return data.get("allowed", [])


def path_to_pattern(path: str) -> re.Pattern:
    """Convert a config path to a regex pattern.

    Supported placeholders:
      {id}    — any single path segment (no slashes)
      {int}   — numeric segment only (e.g. internal PKs)
      {uuid}  — UUID format only (e.g. resource identifiers)
      *       — matches anything including slashes (all sub-paths)
    """
    PLACEHOLDERS = {
        "id":   r"[^/]+",
        "int":  r"[0-9]+",
        "uuid": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    }

    parts = re.split(r"(\{[^}]+\}|\*)", path)
    result = []
    for part in parts:
        if part == "*":
            result.append(".*")
        elif re.match(r"^\{[^}]+\}$", part):
            name = part[1:-1]
            result.append(PLACEHOLDERS.get(name, r"[^/]+"))  # unknown placeholder → generic
        else:
            result.append(re.escape(part))
    return re.compile(f"^{''.join(result)}$")


def is_allowed(path: str, method: str, config: list[dict]) -> bool:
    """Return True if the path+method combination is in the allowlist."""
    for entry in config:
        if path_to_pattern(entry["path"]).match(path):
            methods = [m.upper() for m in entry.get("methods", [])]
            if "*" in methods or method.upper() in methods:
                return True
    return False


def get_proxy_token() -> str:
    token = os.environ.get("PROXY_TOKEN", "").strip()
    if not token:
        log.error("PROXY_TOKEN environment variable is not set")
        sys.exit(1)
    return token


def get_backend_config() -> tuple[str, dict, bool]:
    """Return (base_url, auth_headers, verify_ssl) for the backend API."""
    base_url = os.environ.get("BACKEND_API_ENDPOINT", "").strip().rstrip("/")
    if not base_url:
        log.error("BACKEND_API_ENDPOINT environment variable is not set")
        sys.exit(1)

    verify_ssl = os.environ.get("BACKEND_API_VERIFY_SSL", "true").lower() != "false"

    # Basic auth takes precedence if both user and password are set
    user     = os.environ.get("BACKEND_API_USER", "").strip()
    password = os.environ.get("BACKEND_API_PASSWORD", "").strip()
    if user and password:
        import base64
        credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
        return base_url, {"Authorization": f"Basic {credentials}", "Accept": "application/json"}, verify_ssl

    # Token auth
    token = os.environ.get("BACKEND_API_TOKEN", "").strip()
    if not token:
        log.error("Neither BACKEND_API_TOKEN nor BACKEND_API_USER/PASSWORD are set")
        sys.exit(1)
    scheme = os.environ.get("BACKEND_API_AUTH_SCHEME", "Token").strip()
    return base_url, {"Authorization": f"{scheme} {token}", "Accept": "application/json"}, verify_ssl


@app.before_request
def check_auth():
    if request.path == "/ping":
        return  # health check requires no auth
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        log.warning("401  %s %s  — missing token", request.method, request.path)
        return jsonify({"error": "Unauthorized"}), 401
    if auth[len("Bearer "):] != get_proxy_token():
        log.warning("403  %s %s  — invalid token", request.method, request.path)
        return jsonify({"error": "Forbidden"}), 403


@app.route("/api/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def proxy(subpath):
    path = f"/api/{subpath}"

    try:
        config = load_config()
    except Exception as e:
        log.error("Failed to load config: %s", e)
        return jsonify({"error": "Proxy configuration error"}), 500

    if not is_allowed(path, request.method, config):
        log.warning("403  %s %s  — not in allowlist", request.method, path)
        return jsonify({
            "error": "Not allowed",
            "detail": f"{request.method} {path} is not permitted by proxy configuration"
        }), 403

    base_url, headers, verify_ssl = get_backend_config()
    target_url = base_url + path
    params = dict(request.args)

    # Forward Content-Type for requests with a body
    if request.content_type:
        headers["Content-Type"] = request.content_type

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=params,
            data=request.get_data(),
            timeout=60,
            verify=verify_ssl,
        )
        log.info("%s  %s %s  — forwarded, backend responded %s",
                 resp.status_code, request.method, path, resp.status_code)
        return Response(
            resp.content,
            status=resp.status_code,
            content_type=resp.headers.get("Content-Type", "application/json"),
        )
    except requests.exceptions.RequestException as e:
        log.error("Backend request failed: %s", e)
        return jsonify({"error": "Backend API unreachable", "detail": str(e)}), 502


@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


if __name__ == "__main__":
    # Validate config at startup
    get_proxy_token()
    get_backend_config()
    try:
        config = load_config()
        log.info("Loaded %d allowed endpoint(s) from config", len(config))
    except Exception as e:
        log.error("Cannot load config file: %s", e)
        sys.exit(1)

    base_url, _, _ = get_backend_config()
    port = int(os.environ.get("PROXY_PORT", 8888))
    log.info("API Gatekeeper listening on localhost:%d → %s", port, base_url)
    app.run(host="127.0.0.1", port=port)
