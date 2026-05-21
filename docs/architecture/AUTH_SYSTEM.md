# Auth System

## Overview

The Unsloth_Core auth system uses bearer token authentication with bcrypt-hashed API keys. It supports three roles with granular permissions and provides automatic audit logging for all mutation requests.

## Key Format

API keys are 64-character hexadecimal strings generated via `crypto.randomBytes(32)`:

```
a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
```

- **64 hex chars** = 32 random bytes = 256 bits of entropy
- **First 8 chars** = `key_prefix` — used for fast indexed DB lookup
- **Key is stored as bcrypt hash** (cost 10) — raw key is returned once at creation and cannot be retrieved later

## Three Roles

| Role | Read | Write | Manage Keys |
|------|------|-------|-------------|
| `admin` | All endpoints | All mutations | Yes |
| `operator` | All endpoints | Launch/manage jobs | No |
| `viewer` | All endpoints | Blocked on POST/PUT/PATCH/DELETE | No |

Viewer role enforcement happens in `requireRole()`: if the authenticated key has role `viewer` and the request method is in `["POST", "PUT", "PATCH", "DELETE"]`, the middleware returns 403.

## Bootstrapping the First Key

Before any API requests work, you need to create the first admin API key:

```bash
python scripts/ops/setup_admin_key.py
```

This script:
1. Connects to the local Supabase database (default: `postgresql://postgres:postgres@localhost:15434/postgres`)
2. Generates a random 64-char hex key
3. Hashes it with bcrypt (cost 10)
4. Inserts the hash into `api_keys` table
5. Prints the raw key to stdout

**Save the key immediately** — the bcrypt hash in the database cannot be reversed.

Options:
```bash
# Custom database URL
python scripts/ops/setup_admin_key.py --db-url postgresql://user:pass@host:port/db

# Custom key name
python scripts/ops/setup_admin_key.py --name "production-admin"
```

## How Auth Works

### Middleware Pipeline

1. **`optionalAuth`** (runs on all `/api/*` requests):
   - Reads `Authorization: Bearer <key>` header
   - Extracts the first 8 chars as `key_prefix`
   - Queries `api_keys` table for matching active keys (`SELECT ... WHERE key_prefix = $1 AND is_active = true`)
   - Compares the full key against each bcrypt hash via `bcrypt.compare()`
   - On match: sets `req.apiKey = { id, prefix, name, role }` and updates `last_used_at` (fire-and-forget)
   - On no header: continues silently (does not fail)
   - On invalid header: continues silently (auth is optional at this layer)

2. **`requireRole(...)`** (applied per-route):
   - Checks `req.apiKey` exists (401 if missing)
   - Checks `req.apiKey.role` is in allowed roles (403 if insufficient)
   - Blocks viewer role on write methods (403)
   - Passes to next handler on success

### API Key Management (admin only)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/keys` | GET | List all keys (prefix, name, role, active, last_used) |
| `/api/auth/keys` | POST | Create a new key (body: `{ name, role }`) |
| `/api/auth/keys/:id` | DELETE | Revoke a key (sets `is_active = false`) |

Usage:
```bash
# List keys
curl -H "Authorization: Bearer <admin-key>" http://localhost:3100/api/auth/keys

# Create operator key
curl -X POST -H "Authorization: Bearer <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"name":"ci-bot","role":"operator"}' \
  http://localhost:3100/api/auth/keys

# Revoke key
curl -X DELETE -H "Authorization: Bearer <admin-key>" \
  http://localhost:3100/api/auth/keys/<key-id>
```

## Audit Logging

Every mutation request (POST/PUT/PATCH/DELETE) and every error response (>=400) is automatically logged to the `api_audit_log` table. GET requests with status <400 are skipped.

The audit middleware fires asynchronously on `res.on("finish")` — it never blocks the response.

Logged fields:
- `api_key_id`: Which key made the request (null if anonymous)
- `user_role`: admin, operator, viewer, or anonymous
- `method`, `path`: Request routing info
- `status_code`: Response status
- `request_body`: First 2000 chars, with sensitive fields redacted
- `ip_address`: Client IP (from `req.ip` or `req.socket.remoteAddress`)
- `duration_ms`: Request processing time

### Sensitive Field Redaction

Before logging, the audit middleware recursively redacts values for these keys: `password`, `secret`, `key`, `api_key`, `apiKey`, `token`, `authorization`, `access_token`, `refresh_token`. Redacted values are replaced with `"[REDACTED]"`.

## Key Revocation

To revoke a key (immediately invalidate it):

```sql
UPDATE api_keys SET is_active = false WHERE id = '<key-uuid>';
```

Or use the admin API:
```bash
curl -X DELETE -H "Authorization: Bearer <admin-key>" \
  http://localhost:3100/api/auth/keys/<key-uuid>
```

The `optionalAuth` middleware automatically filters out inactive keys with its `AND is_active = true` query clause.

## Usage Examples

```bash
# Health check (public, no auth needed)
curl http://localhost:3100/api/health

# List jobs (auth required)
curl -H "Authorization: Bearer <key>" http://localhost:3100/api/jobs

# Start a training run (operator or admin)
curl -X POST -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"npcKey":"history_guide","preset":"fast-3b"}' \
  http://localhost:3100/api/training

# Viewer cannot create keys
curl -X POST -H "Authorization: Bearer <viewer-key>" \
  -H "Content-Type: application/json" \
  -d '{"name":"test","role":"operator"}' \
  http://localhost:3100/api/auth/keys
# → 403: "Viewer role cannot perform write operations"
```

## Database Table

See [SUPABASE_SCHEMA.md](SUPABASE_SCHEMA.md) for the full `api_keys` and `api_audit_log` table schemas.
