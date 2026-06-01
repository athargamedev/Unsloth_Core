import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import YAML from "yaml";
import type { RouterDependencies } from "../types";

// ── Module-level cache for YAML registry ─────────────────────────────
let _registryCache: { data: unknown; path: string; mtime: number } | null = null;

function getRegistry(repoRoot: string): unknown {
  const registryPath = path.join(repoRoot, "configs", "parameter-registry.yaml");
  if (!fs.existsSync(registryPath)) return null;
  try {
    const stat = fs.statSync(registryPath);
    if (_registryCache && _registryCache.path === registryPath && _registryCache.mtime === stat.mtimeMs) {
      return _registryCache.data;
    }
    const raw = fs.readFileSync(registryPath, "utf8");
    const parsed = YAML.parse(raw);
    _registryCache = { data: parsed, path: registryPath, mtime: stat.mtimeMs };
    return parsed;
  } catch (err) {
    console.error(`[PARAMS] Error loading registry at ${registryPath}:`, err);
    return null;
  }
}

/**
 * Registers /api/parameters/* routes serving the parameter-registry.yaml.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot } = deps;

  // ── GET /api/parameters — full registry ───────────────────────────
  app.get("/api/parameters", (_req: Request, res: Response) => {
    try {
      const parsed = getRegistry(repoRoot);
      if (!parsed) {
        const registryPath = path.join(repoRoot, "configs", "parameter-registry.yaml");
        const exists = fs.existsSync(registryPath);
        res.status(404).json({ error: "Parameter registry not found", repoRoot, registryPath, exists });
        return;
      }
      res.json(parsed);
    } catch (err) {
      console.error("[PARAMS] Failed to parse parameter registry:", err);
      res.status(500).json({ error: "Failed to parse parameter registry", details: String(err) });
    }
  });

  // ── GET /api/parameters/stages — list stages with counts ──────────
  app.get("/api/parameters/stages", (_req: Request, res: Response) => {
    try {
      const parsed = getRegistry(repoRoot);
      if (!parsed) {
        res.status(404).json({ error: "Parameter registry not found" });
        return;
      }
      const reg = parsed as Record<string, unknown>;
      const params = (reg?.parameters as Record<string, unknown>) || {};
      const stageCounts: Record<string, number> = {};
      for (const val of Object.values(params)) {
        const p = val as Record<string, unknown> | undefined;
        const stage = (p?.stage as string) || "unknown";
        stageCounts[stage] = (stageCounts[stage] || 0) + 1;
      }
      res.json({
        totalParameters: Object.keys(params).length,
        stages: Object.entries(stageCounts).map(([name, count]) => ({ name, count })),
        envVars: reg?.env_vars ? Object.keys(reg.env_vars as Record<string, unknown>).length : 0,
      });
    } catch (err) {
      console.error("[PARAMS] Failed to parse parameter registry:", err);
      res.status(500).json({ error: "Failed to parse parameter registry" });
    }
  });
}
