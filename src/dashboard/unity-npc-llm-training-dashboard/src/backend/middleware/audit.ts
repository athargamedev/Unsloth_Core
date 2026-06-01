import type { Request, Response, NextFunction } from "express";
import { query } from "../lib/db";

// ── Sensitive field redaction ───────────────────────────────────────────────
// Fields whose values are replaced with "[REDACTED]" before logging to prevent
// secrets from being stored in the audit log.
const SENSITIVE_KEYS = new Set([
  "password",
  "secret",
  "key",
  "api_key",
  "apiKey",
  "token",
  "authorization",
  "Authorization",
  "access_token",
  "refresh_token",
]);

function redactBody(body: unknown): unknown {
  if (!body || typeof body !== "object") return body;
  if (Array.isArray(body)) {
    return body.map(redactBody);
  }
  const clone: Record<string, unknown> = { ...body as Record<string, unknown> };
  for (const k of Object.keys(clone)) {
    if (SENSITIVE_KEYS.has(k)) {
      clone[k] = "[REDACTED]";
    } else if (typeof clone[k] === "object" && clone[k] !== null) {
      clone[k] = redactBody(clone[k]);
    }
  }
  return clone;
}

/**
 * Request audit logging middleware.
 * Logs every mutation request (POST, PUT, PATCH, DELETE) and errors to the
 * api_audit_log table. GET requests are skipped unless they result in an error (>=400).
 *
 * Fires asynchronously on response finish — never blocks the request.
 */
export function auditLog(req: Request, res: Response, next: NextFunction): void {
  const startTime = Date.now();

  res.on("finish", () => {
    const duration = Date.now() - startTime;

    // Only log mutations and server/ client errors
    if (req.method === "GET" && res.statusCode < 400) return;

    const apiKeyId: string | null = req.apiKey?.id ?? null;
    const userRole: string = req.apiKey?.role ?? "anonymous";

    const requestBody =
      req.method !== "GET"
        ? JSON.stringify(redactBody(req.body)).substring(0, 2000)
        : null;

    const ipAddress: string | null = req.ip ?? req.socket.remoteAddress ?? null;

    // Fire and forget — never block the response
    query(
      `INSERT INTO api_audit_log (api_key_id, user_role, method, path, status_code, request_body, ip_address, duration_ms)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)`,
      [apiKeyId, userRole, req.method, req.originalUrl ?? req.url, res.statusCode, requestBody, ipAddress, duration],
    ).catch((err: Error) => {
      console.warn("[AUDIT] Failed to log:", err.message);
    });
  });

  next();
}
