import type { Request, Response, NextFunction } from "express";
import bcrypt from "bcrypt";
import { query } from "../lib/db";

// ── Types ──────────────────────────────────────────────────────────────────

type ApiKeyRow = {
  id: string;
  key_hash: string;
  key_prefix: string;
  name: string;
  role: "admin" | "operator" | "viewer";
  is_active: boolean;
  [key: string]: unknown;
};

type ApiKeyListItem = {
  id: string;
  key_prefix: string;
  name: string;
  role: string;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
  [key: string]: unknown;
};

// Extend Express Request to include auth info
declare global {
  namespace Express {
    interface Request {
      apiKey?: {
        id: string;
        prefix: string;
        name: string;
        role: "admin" | "operator" | "viewer";
      };
    }
  }
}

// ── Constants ──────────────────────────────────────────────────────────────

const BEARER_PREFIX = "Bearer ";
const WRITE_METHODS = ["POST", "PUT", "PATCH", "DELETE"];

// ── Key Management ─────────────────────────────────────────────────────────

/**
 * Hash an API key for storage using bcrypt.
 */
export async function hashApiKey(key: string): Promise<string> {
  return bcrypt.hash(key, 10);
}

/**
 * Generate a new API key with a random 64-char hex token.
 * Inserts the bcrypt hash into the api_keys table.
 * Returns the raw key only once — caller must save it.
 */
export async function generateApiKey(
  name: string,
  role: "admin" | "operator" | "viewer" = "admin",
): Promise<{ key: string; prefix: string; hash: string }> {
  const crypto = await import("crypto");
  const raw = crypto.randomBytes(32).toString("hex"); // 64-char hex key
  const prefix = raw.substring(0, 8);
  const hash = await hashApiKey(raw);

  await query(
    "INSERT INTO api_keys (key_hash, key_prefix, name, role) VALUES ($1, $2, $3, $4)",
    [hash, prefix, name, role],
  );

  return { key: raw, prefix, hash };
}

/**
 * List all API keys (without hashes).
 */
export async function listApiKeys(): Promise<ApiKeyListItem[]> {
  const rows = await query<ApiKeyListItem>(
    "SELECT id, key_prefix, name, role, is_active, last_used_at, created_at FROM api_keys ORDER BY created_at DESC",
    [],
  );
  return rows;
}

/**
 * Revoke an API key by setting is_active = false.
 * Returns true if a row was updated.
 */
export async function revokeApiKey(keyId: string): Promise<boolean> {
  const result = await query<{ id: string }>(
    "UPDATE api_keys SET is_active = false WHERE id = $1 RETURNING id",
    [keyId],
  );
  return result.length > 0;
}

// ── Middleware ──────────────────────────────────────────────────────────────

/**
 * Main auth middleware.
 * Validates the Bearer token from the Authorization header against
 * bcrypt hashes in the api_keys table.
 */
export async function requireAuth(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith(BEARER_PREFIX)) {
    res
      .status(401)
      .json({ error: "Missing or invalid Authorization header. Use: Bearer <api_key>" });
    return;
  }

  const key = authHeader.substring(BEARER_PREFIX.length).trim();
  if (!key) {
    res.status(401).json({ error: "Empty API key" });
    return;
  }

  try {
    // Look up by prefix (first 8 chars) for an efficient indexed query
    const prefix = key.substring(0, 8);
    const rows = await query<ApiKeyRow>(
      "SELECT id, key_hash, key_prefix, name, role, is_active FROM api_keys WHERE key_prefix = $1 AND is_active = true",
      [prefix],
    );

    if (rows.length === 0) {
      res.status(401).json({ error: "Invalid API key" });
      return;
    }

    // Find the matching key by full bcrypt comparison
    let matched = false;
    for (const row of rows) {
      const isValid = await bcrypt.compare(key, row.key_hash);
      if (isValid) {
        req.apiKey = {
          id: row.id,
          prefix: row.key_prefix,
          name: row.name,
          role: row.role,
        };
        matched = true;

        // Update last_used_at in background — don't block the request
        query("UPDATE api_keys SET last_used_at = NOW() WHERE id = $1", [row.id]).catch(
          () => {
            /* swallow background update errors */
          },
        );
        break;
      }
    }

    if (!matched) {
      res.status(401).json({ error: "Invalid API key" });
      return;
    }

    next();
  } catch (err) {
    console.error("[AUTH] Database error:", err);
    res.status(500).json({ error: "Authentication service unavailable" });
  }
}

/**
 * Role-based access control middleware factory.
 * Checks req.apiKey.role against the allowed roles.
 * Viewer role is additionally blocked from write methods.
 */
export function requireRole(...roles: string[]) {
  return (req: Request, res: Response, next: NextFunction): void => {
    if (!req.apiKey) {
      res.status(401).json({ error: "Authentication required" });
      return;
    }

    if (!roles.includes(req.apiKey.role)) {
      res
        .status(403)
        .json({ error: `Insufficient permissions. Required role: ${roles.join(" or ")}` });
      return;
    }

    // Viewer role: block write operations
    if (req.apiKey.role === "viewer" && WRITE_METHODS.includes(req.method)) {
      res.status(403).json({ error: "Viewer role cannot perform write operations" });
      return;
    }

    next();
  };
}

/**
 * Optional auth — does not fail if no Authorization header is present.
 * If a valid Bearer token is provided, sets req.apiKey.
 * Otherwise continues silently.
 */
export async function optionalAuth(
  req: Request,
  res: Response,
  next: NextFunction,
): Promise<void> {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith(BEARER_PREFIX)) {
    next();
    return;
  }

  // Header present — try to validate but don't fail
  try {
    const key = authHeader.substring(BEARER_PREFIX.length).trim();
    const prefix = key.substring(0, 8);
    const rows = await query<ApiKeyRow>(
      "SELECT id, key_hash, key_prefix, name, role, is_active FROM api_keys WHERE key_prefix = $1 AND is_active = true",
      [prefix],
    );

    for (const row of rows) {
      const isValid = await bcrypt.compare(key, row.key_hash);
      if (isValid) {
        req.apiKey = {
          id: row.id,
          prefix: row.key_prefix,
          name: row.name,
          role: row.role,
        };
        break;
      }
    }
  } catch {
    // Ignore auth errors in optional mode
  }

  next();
}
