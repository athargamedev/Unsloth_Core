import type { Express, Request, Response } from "express";
import { requireRole } from "../middleware/auth";
import { generateApiKey, listApiKeys, revokeApiKey } from "../middleware/auth";

/**
 * Registers /api/auth/keys endpoints for API key management.
 * All endpoints require the admin role (requireAuth is applied globally in index.ts).
 */
export function registerRoutes(app: Express): void {
  // ── GET /api/auth/keys — List all API keys (admin only) ──────────────────
  app.get(
    "/api/auth/keys",
    requireRole("admin"),
    async (_req: Request, res: Response) => {
      try {
        const keys = await listApiKeys();
        res.json(keys);
      } catch (err) {
        console.error("[AUTH] Failed to list API keys:", err);
        res.status(500).json({ error: "Failed to list API keys" });
      }
    },
  );

  // ── POST /api/auth/keys — Generate a new API key (admin only) ────────────
  app.post(
    "/api/auth/keys",
    requireRole("admin"),
    async (req: Request, res: Response) => {
      const { name, role } = req.body as { name?: string; role?: string };

      if (!name || typeof name !== "string" || name.trim().length === 0) {
        res.status(400).json({ error: "Name is required" });
        return;
      }

      const validRoles = ["admin", "operator", "viewer"] as const;
      const resolvedRole = validRoles.includes(role as "admin" | "operator" | "viewer")
        ? (role as "admin" | "operator" | "viewer")
        : "operator";

      try {
        const { key, prefix } = await generateApiKey(name.trim(), resolvedRole);
        res.status(201).json({
          key,
          prefix,
          name: name.trim(),
          role: resolvedRole,
          message: "Save this key immediately. It cannot be retrieved later.",
        });
      } catch (err) {
        console.error("[AUTH] Failed to generate API key:", err);
        res.status(500).json({ error: "Failed to generate API key" });
      }
    },
  );

  // ── DELETE /api/auth/keys/:id — Revoke an API key (admin only) ───────────
  app.delete(
    "/api/auth/keys/:id",
    requireRole("admin"),
    async (req: Request, res: Response) => {
      const keyId = req.params.id;

      if (!keyId || typeof keyId !== "string") {
        res.status(400).json({ error: "Key ID is required" });
        return;
      }

      try {
        const revoked = await revokeApiKey(keyId);
        if (!revoked) {
          res.status(404).json({ error: "API key not found" });
          return;
        }
        res.json({ message: "API key revoked", id: keyId });
      } catch (err) {
        console.error("[AUTH] Failed to revoke API key:", err);
        res.status(500).json({ error: "Failed to revoke API key" });
      }
    },
  );
}
