1|# Auth System
2|
3|## Overview
4|
5|The Unsloth_Core auth system uses bearer token authentication with bcrypt-hashed API keys. It supports three roles with granular permissions and provides automatic audit logging for all mutation requests.
6|
7|## Key Format
8|
9|API keys are 64-character hexadecimal strings generated via `crypto.randomBytes(32)`:
10|
11|```
12|a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2
13|```
14|
15|- **64 hex chars** = 32 random bytes = 256 bits of entropy
16|- **First 8 chars** = `key_prefix` — used for fast indexed DB lookup
17|- **Key is stored as bcrypt hash** (cost 10) — raw key is returned once at creation and cannot be retrieved later
18|
19|## Three Roles
20|
21|| Role | Read | Write | Manage Keys |
22||------|------|-------|-------------|
23|| `admin` | All endpoints | All mutations | Yes |
24|| `operator` | All endpoints | Launch/manage jobs | No |
25|| `viewer` | All endpoints | Blocked on POST/PUT/PATCH/DELETE | No |
26|
27|Viewer role enforcement happens in `requireRole()`: if the authenticated key has role `viewer` and the request method is in `["POST", "PUT", "PATCH", "DELETE"]`, the middleware returns 403.
28|
29|## Bootstrapping the First Key
30|
31|Before any API requests work, you need to create the first admin API key:
32|
33|```bash
34|python scripts/ops/setup_admin_key.py
35|```
36|
37|This script:
38|1. Connects to the local Supabase database (default: `postgresql://postgres:***@localhost:15434/postgres`)
39|2. Generates a random 64-char hex key
40|3. Hashes it with bcrypt (cost 10)
41|4. Inserts the hash into `api_keys` table
42|5. Prints the raw key to stdout
43|
44|**Save the key immediately** — the bcrypt hash in the database cannot be reversed.
45|
46|Options:
47|```bash
48|# Custom database URL
49|python scripts/ops/setup_admin_key.py --db-url postgresql://user:***@host:port/db
50|
51|# Custom key name
52|python scripts/ops/setup_admin_key.py --name "production-admin"
53|```
54|
55|## How Auth Works
56|
57|### Middleware Pipeline
58|
59|1. **`optionalAuth`** (runs on all `/api/*` requests):
60|   - Reads `Authorization: Bearer *** header
61|   - Extracts the first 8 chars as `key_prefix`
62|   - Queries `api_keys` table for matching active keys (`SELECT ... WHERE key_prefix = $1 AND is_active = true`)
63|   - Compares the full key against each bcrypt hash via `bcrypt.compare()`
64|   - On match: sets `req.apiKey = { id, prefix, name, role }` and updates `last_used_at` (fire-and-forget)
65|   - On no header: continues silently (does not fail)
66|   - On invalid header: continues silently (auth is optional at this layer)
67|
68|2. **`requireRole(...)`** (applied per-route):
69|   - Checks `req.apiKey` exists (401 if missing)
70|   - Checks `req.apiKey.role` is in allowed roles (403 if insufficient)
71|   - Blocks viewer role on write methods (403)
72|   - Passes to next handler on success
73|
74|### API Key Management (admin only)
75|
76|| Endpoint | Method | Description |
77||----------|--------|-------------|
78|| `/api/auth/keys` | GET | List all keys (prefix, name, role, active, last_used) |
79|| `/api/auth/keys` | POST | Create a new key (body: `{ name, role }`) |
80|| `/api/auth/keys/:id` | DELETE | Revoke a key (sets `is_active = false`) |
81|
82|Usage:
83|```bash
84|# List keys
85|curl -H "Authorization: Bearer *** http://localhost:3100/api/auth/keys
86|
87|# Create operator key
88|curl -X POST -H "Authorization: Bearer *** \
89|  -H "Content-Type: application/json" \
90|  -d '{"name":"ci-bot","role":"operator"}' \
91|  http://localhost:3100/api/auth/keys
92|
93|# Revoke key
94|curl -X DELETE -H "Authorization: Bearer *** \
95|  http://localhost:3100/api/auth/keys/<key-id>
96|```
97|
98|## Audit Logging
99|
100|Every mutation request (POST/PUT/PATCH/DELETE) and every error response (>=400) is automatically logged to the `api_audit_log` table. GET requests with status <400 are skipped.
101|
102|The audit middleware fires asynchronously on `res.on("finish")` — it never blocks the response.
103|
104|Logged fields:
105|- `api_key_id`: Which key made the request (null if anonymous)
106|- `user_role`: admin, operator, viewer, or anonymous
107|- `method`, `path`: Request routing info
108|- `status_code`: Response status
109|- `request_body`: First 2000 chars, with sensitive fields redacted
110|- `ip_address`: Client IP (from `req.ip` or `req.socket.remoteAddress`)
111|- `duration_ms`: Request processing time
112|
113|### Sensitive Field Redaction
114|
115|Before logging, the audit middleware recursively redacts values for these keys: `password`, `secret`, `key`, `api_key`, `apiKey`, `token`, `authorization`, `access_token`, `refresh_token`. Redacted values are replaced with `"[REDACTED]"`.
116|
117|## Key Revocation
118|
119|To revoke a key (immediately invalidate it):
120|
121|```sql
122|UPDATE api_keys SET is_active = false WHERE id = '<key-uuid>';
123|```
124|
125|Or use the admin API:
126|```bash
127|curl -X DELETE -H "Authorization: Bearer *** \
128|  http://localhost:3100/api/auth/keys/<key-uuid>
129|```
130|
131|The `optionalAuth` middleware automatically filters out inactive keys with its `AND is_active = true` query clause.
132|
133|## Usage Examples
134|
135|```bash
136|# Health check (public, no auth needed)
137|curl http://localhost:3100/api/health
138|
139|# List jobs (auth required)
140|curl -H "Authorization: Bearer *** http://localhost:3100/api/jobs
141|
142|# Start a training run (operator or admin)
143|curl -X POST -H "Authorization: Bearer *** \
144|  -H "Content-Type: application/json" \
145|  -d '{"npcKey":"history_guide","preset":"fast-3b"}' \
146|  http://localhost:3100/api/training
147|
148|# Viewer cannot create keys
149|curl -X POST -H "Authorization: Bearer *** \
150|  -H "Content-Type: application/json" \
151|  -d '{"name":"test","role":"operator"}' \
152|  http://localhost:3100/api/auth/keys
153|# → 403: "Viewer role cannot perform write operations"
154|```
155|
156|## Database Table
157|
158|See [supabase-schema.md](supabase-schema.md) for the full `api_keys` and `api_audit_log` table schemas.
159|