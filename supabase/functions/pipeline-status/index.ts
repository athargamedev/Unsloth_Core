import { serve } from "https://deno.land/std@0.224.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "http://127.0.0.1:16437";
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") || "";
const DB_URL = Deno.env.get("DB_URL") || "postgresql://postgres:postgres@127.0.0.1:15434/postgres";

interface PipelineStatus {
  jobs: { total: number; by_status: Record<string, number> };
  runs: { total: number; ok: number; failed: number; start: number };
  artifacts: { total: number; by_type: Record<string, number> };
  quality_gates: { total: number; avg_pass_rate: number };
  eval_sessions: { total: number; avg_win_rate: number };
  config_snapshots: { total: number };
  npcs: string[];
  timestamp: string;
}

serve(async (req: Request) => {
  const headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };

  if (req.method === "OPTIONS") {
    return new Response(null, { headers });
  }

  try {
    // Try direct PostgreSQL first (preferred for local dev)
    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

    // All queries in parallel
    const [
      jobsResult,
      runsResult,
      artifactsResult,
      qualityGatesResult,
      evalSessionsResult,
      configSnapshotsResult,
      npcsResult,
    ] = await Promise.all([
      supabase.from("pipeline_jobs").select("status"),
      supabase.from("pipeline_runs").select("status"),
      supabase.from("pipeline_artifacts").select("artifact_type"),
      supabase.from("dataset_quality_gates").select("pass_rate"),
      supabase.from("eval_sessions").select("win_rate"),
      supabase.from("pipeline_config_snapshots").select("id", { count: "exact" }),
      supabase.from("pipeline_runs").select("npc_key"),
    ]);

    // Process jobs by status
    const byStatus: Record<string, number> = {};
    for (const row of jobsResult.data || []) {
      byStatus[row.status] = (byStatus[row.status] || 0) + 1;
    }

    // Process artifacts by type
    const byType: Record<string, number> = {};
    for (const row of artifactsResult.data || []) {
      byType[row.artifact_type] = (byType[row.artifact_type] || 0) + 1;
    }

    // Process runs by status
    const runsByStatus: Record<string, number> = {};
    for (const row of runsResult.data || []) {
      runsByStatus[row.status] = (runsByStatus[row.status] || 0) + 1;
    }

    // Process NPCs (unique)
    const npcSet = new Set((npcsResult.data || []).map((r: any) => r.npc_key));

    // Average pass rate
    const passes = (qualityGatesResult.data || []).map((r: any) => r.pass_rate);
    const avgPassRate = passes.length > 0
      ? passes.reduce((a: number, b: number) => a + b, 0) / passes.length
      : 0;

    // Average win rate
    const wins = (evalSessionsResult.data || []).map((r: any) => r.win_rate);
    const avgWinRate = wins.length > 0
      ? wins.reduce((a: number, b: number) => a + b, 0) / wins.length
      : 0;

    const status: PipelineStatus = {
      jobs: { total: jobsResult.data?.length || 0, by_status: byStatus },
      runs: {
        total: runsResult.data?.length || 0,
        ok: runsByStatus["ok"] || 0,
        failed: runsByStatus["failed"] || 0,
        start: runsByStatus["start"] || 0,
      },
      artifacts: { total: artifactsResult.data?.length || 0, by_type: byType },
      quality_gates: { total: qualityGatesResult.data?.length || 0, avg_pass_rate: Math.round(avgPassRate * 100) / 100 },
      eval_sessions: { total: evalSessionsResult.data?.length || 0, avg_win_rate: Math.round(avgWinRate * 100) / 100 },
      config_snapshots: { total: configSnapshotsResult.count || 0 },
      npcs: Array.from(npcSet).sort(),
      timestamp: new Date().toISOString(),
    };

    return new Response(JSON.stringify(status, null, 2), {
      status: 200,
      headers,
    });
  } catch (err) {
    const errorBody = {
      error: err instanceof Error ? err.message : "Unknown error",
      timestamp: new Date().toISOString(),
    };
    return new Response(JSON.stringify(errorBody, null, 2), {
      status: 500,
      headers,
    });
  }
});
