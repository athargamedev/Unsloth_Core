import { execFileSync } from "child_process";
import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import type { RouterDependencies } from "../types";

/**
 * Registers /api/exports/* and /api/unity/* routes.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot } = deps;

  // ── GET /api/exports ───────────────────────────────────────────────
  app.get("/api/exports", (_req: Request, res: Response) => {
    const exportsRoot = path.join(repoRoot, "exports");
    if (!fs.existsSync(exportsRoot)) {
      res.json([]);
      return;
    }

    const entries: Array<{
      npcKey: string;
      file: string;
      updatedAt: string;
    }> = [];

    for (const npcKey of fs.readdirSync(exportsRoot)) {
      const npcDir = path.join(exportsRoot, npcKey);
      if (!fs.statSync(npcDir).isDirectory()) continue;
      for (const file of fs.readdirSync(npcDir).filter((f) =>
        f.endsWith(".gguf"),
      )) {
        const stat = fs.statSync(path.join(npcDir, file));
        entries.push({
          npcKey,
          file: `exports/${npcKey}/${file}`,
          updatedAt: stat.mtime.toISOString(),
        });
      }
    }

    res.json(entries);
  });

  // ── GET /api/unity/status ──────────────────────────────────────────
  app.get("/api/unity/status", (_req: Request, res: Response) => {
    const exportsRoot = path.join(repoRoot, "exports");
    const npcs: Array<{
      npcKey: string;
      ggufFiles: Array<{
        name: string;
        sizeMB: number;
        quant: string;
      }>;
      manifest: Record<string, unknown>;
    }> = [];

    if (fs.existsSync(exportsRoot)) {
      for (const npcDir of fs.readdirSync(exportsRoot)) {
        const npcPath = path.join(exportsRoot, npcDir);
        if (!fs.statSync(npcPath).isDirectory()) continue;

        const ggufFiles = fs
          .readdirSync(npcPath)
          .filter((f) => f.endsWith(".gguf"))
          .map((f) => {
            const stat = fs.statSync(path.join(npcPath, f));
            const quant = f.includes("q4_k_m")
              ? "q4_k_m"
              : f.includes("f16")
                ? "f16"
                : f.includes("q8_0")
                  ? "q8_0"
                  : "unknown";
            return {
              name: f,
              sizeMB:
                Math.round(stat.size / (1024 * 1024) * 10) / 10,
              quant,
            };
          });

        let manifest: Record<string, unknown> = {};
        const manifestPath = path.join(npcPath, "manifest.json");
        if (fs.existsSync(manifestPath)) {
          try {
            manifest = JSON.parse(
              fs.readFileSync(manifestPath, "utf8"),
            );
          } catch {
            // ignore
          }
        }

        npcs.push({ npcKey: npcDir, ggufFiles, manifest });
      }
    }

    // Detect Unity project
    let unityProjectPath = "";
    const parent = path.resolve(repoRoot, "..");
    if (fs.existsSync(parent)) {
      const candidates = fs.readdirSync(parent).filter((entry) => {
        const entryPath = path.join(parent, entry);
        if (entry === path.basename(repoRoot)) return false;
        try {
          return (
            fs.statSync(path.join(entryPath, "Assets")).isDirectory() &&
            fs.statSync(path.join(entryPath, "ProjectSettings")).isDirectory()
          );
        } catch {
          return false;
        }
      });
      if (candidates.length > 0) {
        unityProjectPath = path.resolve(parent, candidates[0]);
      }
    }

    const streamingModelsPath = unityProjectPath
      ? path.join(
          unityProjectPath,
          "Assets",
          "StreamingAssets",
          "Models",
        )
      : "";
    const deployedFiles: string[] = [];
    if (streamingModelsPath && fs.existsSync(streamingModelsPath)) {
      const files = fs
        .readdirSync(streamingModelsPath)
        .filter((f) => f.endsWith(".gguf"));
      for (const f of files) {
        const fPath = path.join(streamingModelsPath, f);
        const stat = fs.statSync(fPath);
        deployedFiles.push(
          `${f} (${Math.round(stat.size / (1024 * 1024))}MB)`,
        );
      }
    }

    res.json({
      exported: npcs,
      unityProject: unityProjectPath || null,
      deployedFiles,
      deployScript: fs.existsSync(
        path.join(repoRoot, "scripts", "deploy_to_unity.py"),
      ),
    });
  });

  // ── POST /api/unity/deploy ─────────────────────────────────────────
  app.post("/api/unity/deploy", (req: Request, res: Response) => {
    try {
      const dryRun = req.body?.dryRun === true;
      const cmd = ["./ucore", "deploy"];
      if (dryRun) cmd.push("--dry-run");
      if (req.body?.unityProject) {
        const project = String(req.body.unityProject);
        // Prevent path traversal: only allow alphanumeric, dashes, underscores, slashes, and dots.
        if (!/^[a-zA-Z0-9_./-]+$/.test(project)) {
          res.status(400).json({ success: false, error: "Invalid unityProject path" });
          return;
        }
        cmd.push("--unity-project", project);
      }
      if (req.body?.skipExport === true) cmd.push("--skip-export");
      if (req.body?.exportOnly === true) cmd.push("--export-only");

      const result = execFileSync(cmd[0], cmd.slice(1), {
        cwd: repoRoot,
        encoding: "utf8",
        timeout: 30000,
      });
      res.json({
        success: true,
        output: result.trim(),
        dryRun,
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Deploy failed";
      res.status(500).json({ success: false, error: message });
    }
  });
}
