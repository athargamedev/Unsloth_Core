import type { Express, Request, Response } from "express";
import type { RouterDependencies } from "../types";

/**
 * Registers /api/supabase/* routes.
 * These proxy to the configured Supabase REST API.
 */
export function registerRoutes(app: Express, _deps: RouterDependencies): void {
  const supabaseUrl = process.env.SUPABASE_URL || "";
  const supabaseKey = process.env.SUPABASE_KEY || "";

  // ── GET /api/supabase/status ────────────────────────────────────────────
  app.get("/api/supabase/status", async (_req: Request, res: Response) => {
    if (!supabaseUrl || !supabaseKey) {
      res.json({
        connected: false,
        url: "",
        error: "SUPABASE_URL and SUPABASE_KEY not configured",
      });
      return;
    }
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      let apiResponse: globalThis.Response | undefined;
      try {
        apiResponse = await fetch(
          `${supabaseUrl}/rest/v1/npc_profiles?select=npc_id&limit=1`,
          {
            headers: {
              apikey: supabaseKey,
              Authorization: `Bearer ${supabaseKey}`,
            },
            signal: controller.signal,
          },
        );
      } finally {
        clearTimeout(timeout);
      }
      res.json({
        connected: apiResponse.ok,
        url: supabaseUrl,
        error: apiResponse.ok
          ? undefined
          : `Health check failed: ${apiResponse.status}`,
      });
    } catch (err: unknown) {
      res.json({
        connected: false,
        url: supabaseUrl,
        error: err instanceof Error ? err.message : "Unknown error",
      });
    }
  });

  // ── GET /api/supabase/leaderboard ──────────────────────────────────────
  app.get(
    "/api/supabase/leaderboard",
    async (_req: Request, res: Response) => {
      if (!supabaseUrl || !supabaseKey) {
        res.json({
          entries: [],
          status: {
            connected: false,
            url: "",
            error: "Supabase not configured",
          },
        });
        return;
      }
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        let apiResponse: globalThis.Response;
        try {
          apiResponse = await fetch(
            `${supabaseUrl}/rest/v1/test_results?select=*&order=score.desc&limit=20`,
            {
              headers: {
                apikey: supabaseKey,
                Authorization: `Bearer ${supabaseKey}`,
              },
              signal: controller.signal,
            },
          );
        } finally {
          clearTimeout(timeout);
        }
        if (!apiResponse.ok)
          throw new Error(`Supabase query failed: ${apiResponse.status}`);
        const data: Array<Record<string, unknown>> =
          await apiResponse.json();
        const entries = data.map(
          (row: Record<string, unknown>, i: number) => ({
            rank: i + 1,
            npc_id: row.npc_id,
            npc_name: row.npc_id,
            test_name: row.test_name,
            score: row.score,
            metrics: row.metrics || {},
          }),
        );
        res.json({
          entries,
          status: { connected: true, url: supabaseUrl },
        });
      } catch (err: unknown) {
        res.json({
          entries: [],
          status: {
            connected: false,
            url: supabaseUrl,
            error:
              err instanceof Error ? err.message : "Unknown error",
          },
        });
      }
    },
  );

  // ── GET /api/supabase/npc-profiles ─────────────────────────────────────
  app.get(
    "/api/supabase/npc-profiles",
    async (_req: Request, res: Response) => {
      if (!supabaseUrl || !supabaseKey) {
        res.json({
          profiles: [],
          status: {
            connected: false,
            url: "",
            error: "Supabase not configured",
          },
        });
        return;
      }
      try {
        const apiResponse = await fetch(
          `${supabaseUrl}/rest/v1/npc_profiles?select=*&order=created_at.desc`,
          {
            headers: {
              apikey: supabaseKey,
              Authorization: `Bearer ${supabaseKey}`,
            },
          },
        );
        if (!apiResponse.ok)
          throw new Error(
            `Supabase query failed: ${apiResponse.status}`,
          );
        const result = await apiResponse.json();
        res.json({
          profiles: result,
          status: { connected: true, url: supabaseUrl },
        });
      } catch (err: unknown) {
        res.json({
          profiles: [],
          status: {
            connected: false,
            url: supabaseUrl,
            error:
              err instanceof Error ? err.message : "Unknown error",
          },
        });
      }
    },
  );
}
