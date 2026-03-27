# API Gatekeeper

A lightweight allowlist-based proxy for controlled access to backend APIs. Designed for situations where a client needs restricted access to a powerful API. Also hides your API credentials from the client. For maximum separation, run the proxy in a different context where the client has no read access to any of the files, especially `start_proxy.sh`, where the API credentials are stored.

## How it works

```
Client → API Gatekeeper (PROXY_TOKEN) → allowlist check → Backend API (backend credentials)
```

- The client authenticates against the proxy with `PROXY_TOKEN`
- The proxy checks the request path and method against `proxy_config.yaml`
- Allowed requests are forwarded to the backend API using the configured backend credentials
- Everything else is blocked with a 403
- You can change `proxy_config.yaml` while the proxy is running — the config is read on every request.

The backend credentials are never exposed to the client.

## Installation

**Debian/Ubuntu:**
```bash
sudo apt install python3-flask python3-requests python3-yaml
```

**pip:**
```bash
pip install -r requirements.txt
```

## Configuration

Copy `start_proxy.sh` and fill in your values:

```bash
cp start_proxy.sh my_start_proxy.sh
# edit my_start_proxy.sh — never commit files with real credentials
```

**Backend token auth:**
```bash
BACKEND_API_TOKEN=your-api-token
BACKEND_API_AUTH_SCHEME=Token          # or Bearer
BACKEND_API_ENDPOINT=https://your.api.domain/
BACKEND_API_VERIFY_SSL=true            # set to false for self-signed certs
```

**Backend basic auth:**
```bash
BACKEND_API_USER=username
BACKEND_API_PASSWORD=mysecret
BACKEND_API_ENDPOINT=https://your.api.domain/
```

**Proxy settings:**
```bash
PROXY_TOKEN=choose-a-strong-secret    # clients use this to authenticate
PROXY_PORT=8888                       # defaults to 8888
```

## Allowlist

Edit `proxy_config.yaml` to define which endpoints and methods are permitted:

```yaml
allowed:
  # Read-only collection and items
  - path: /api/users/
    methods: [GET]
  - path: /api/users/{uuid}/
    methods: [GET]

  # Allow writes but not delete
  - path: /api/items/
    methods: [GET, POST]
  - path: /api/items/{uuid}/
    methods: [GET, PUT, PATCH]

  # Numeric ID with wildcard sub-paths
  - path: /api/contracts/{int}/*
    methods: [GET]
```

**Path placeholders:**

| Placeholder | Matches |
|---|---|
| `{id}` | Any single path segment (no slashes) |
| `{int}` | Numeric segments only (e.g. `42`, `8756`) |
| `{uuid}` | UUID format only (e.g. `550e8400-e29b-41d4-a716-446655440000`) |
| `*` | Anything including slashes (all sub-paths) |

The config is reloaded on every request — no restart needed when updating the allowlist.

## Running

```bash
bash my_start_proxy.sh
```

The proxy listens on `localhost` only — expose it further only if you understand the implications.

## Using the proxy

```bash
curl -H "Authorization: Bearer $PROXY_TOKEN" http://localhost:8888/api/users/
```

Health check (no auth required):
```bash
curl http://localhost:8888/ping
```

## License

MIT — see [LICENSE](LICENSE).
