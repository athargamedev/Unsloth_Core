import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import type { RouterDependencies } from "../types";

/**
 * Registers /api/datasets/* and /api/subjects routes.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot } = deps;

  // ── GET /api/datasets ─────────────────────────────────────────────
  app.get("/api/datasets", (_req: Request, res: Response) => {
    const datasetsRoot = path.join(repoRoot, "subjects", "datasets");
    if (!fs.existsSync(datasetsRoot)) {
      res.json([]);
      return;
    }

    const result = fs
      .readdirSync(datasetsRoot)
      .map((npcKey: string) => {
        const npcPath = path.join(datasetsRoot, npcKey);
        if (!fs.statSync(npcPath).isDirectory()) return null;

        const versions = fs
          .readdirSync(npcPath)
          .filter((technique: string) =>
            fs.statSync(path.join(npcPath, technique)).isDirectory(),
          )
          .map((technique: string) => {
            const trainPath = path.join(npcPath, technique, "train.jsonl");
            const entries = fs.existsSync(trainPath)
              ? fs.readFileSync(trainPath, "utf8").split("\n").filter(Boolean).length
              : 0;
            const stat = fs.existsSync(trainPath)
              ? fs.statSync(trainPath)
              : fs.statSync(path.join(npcPath, technique));
            return {
              tag: technique,
              size: `${Math.max(1, Math.round(stat.size / 1024))}KB`,
              entries,
              createdAt: stat.mtime.toISOString(),
            };
          });

        return { id: npcKey, name: npcKey, versions };
      })
      .filter(Boolean);

    res.json(result);
  });

  // ── GET /api/subjects ──────────────────────────────────────────────
  app.get("/api/subjects", (_req: Request, res: Response) => {
    const specsDir = path.join(repoRoot, "subjects", "NPC_specs");
    if (!fs.existsSync(specsDir)) {
      res.json([]);
      return;
    }

    const subjects = fs
      .readdirSync(specsDir)
      .filter((f: string) => f.endsWith(".json"))
      .map((file: string) => ({
        id: file.replace(/\.json$/, ""),
        path: `subjects/NPC_specs/${file}`,
      }));

    res.json(subjects);
  });

  // ── GET /api/datasets/quality-summary ──────────────────────────────
  app.get("/api/datasets/quality-summary", (_req: Request, res: Response) => {
    const datasetsDir = path.join(repoRoot, "subjects", "datasets");
    if (!fs.existsSync(datasetsDir)) {
      res.json([]);
      return;
    }

    try {
      const results: Array<{
        npcKey: string;
        technique: string;
        path: string;
        summary: Record<string, unknown>;
      }> = [];
      const npcDirs = fs.readdirSync(datasetsDir);
      for (const npcKey of npcDirs) {
        const npcDir = path.join(datasetsDir, npcKey);
        if (!fs.statSync(npcDir).isDirectory()) continue;
        const techniqueDirs = fs.readdirSync(npcDir);
        for (const technique of techniqueDirs) {
          const summaryPath = path.join(npcDir, technique, "quality_summary.json");
          if (fs.existsSync(summaryPath)) {
            try {
              const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
              results.push({
                npcKey,
                technique,
                path: `subjects/datasets/${npcKey}/${technique}/quality_summary.json`,
                summary,
              });
            } catch {
              // skip malformed
            }
          }
        }
      }
      res.json(results);
    } catch (err) {
      res.status(500).json({
        error: "Failed to list quality summaries",
      });
    }
  });

  // ── GET /api/datasets/quality-summary/:npcKey/:technique ──────────
  function validateKey(key: string): boolean {
    return /^[a-z][a-z0-9_]*$/.test(key);
  }

  app.get(
    "/api/datasets/quality-summary/:npcKey/:technique",
    (req: Request, res: Response) => {
      const { npcKey, technique } = req.params;
      if (!npcKey || !technique) {
        res.status(400).json({ error: "npcKey and technique are required" });
        return;
      }
      if (!validateKey(npcKey) || !validateKey(technique)) {
        res.status(400).json({ error: "Invalid NPC key or technique" });
        return;
      }

      const summaryPath = path.join(
        repoRoot,
        "subjects",
        "datasets",
        npcKey,
        technique,
        "quality_summary.json",
      );
      if (
        !summaryPath.startsWith(path.join(repoRoot, "subjects", "datasets"))
      ) {
        res.status(400).json({ error: "Invalid path" });
        return;
      }
      if (!fs.existsSync(summaryPath)) {
        res.status(404).json({
          error: `Quality summary not found for ${npcKey}/${technique}`,
        });
        return;
      }
      try {
        const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
        res.json(summary);
      } catch {
        res.status(500).json({ error: "Failed to load quality summary" });
      }
    },
  );

  // ── GET /api/datasets/quality-failures/:npcKey/:technique ─────────
  app.get(
    "/api/datasets/quality-failures/:npcKey/:technique",
    (req: Request, res: Response) => {
      const { npcKey, technique } = req.params;
      if (!npcKey || !technique) {
        res.status(400).json({ error: "npcKey and technique are required" });
        return;
      }
      if (!validateKey(npcKey) || !validateKey(technique)) {
        res.status(400).json({ error: "Invalid NPC key or technique" });
        return;
      }

      const summaryPath = path.join(
        repoRoot,
        "subjects",
        "datasets",
        npcKey,
        technique,
        "quality_summary.json",
      );
      let failuresPath: string | null = null;

      if (fs.existsSync(summaryPath)) {
        try {
          const summary = JSON.parse(fs.readFileSync(summaryPath, "utf8"));
          if (summary.failures_path) {
            const candidatePath = path.join(repoRoot, summary.failures_path);
            if (
              candidatePath.startsWith(repoRoot) &&
              fs.existsSync(candidatePath)
            ) {
              failuresPath = candidatePath;
            }
          }
        } catch {
          // fall through
        }
      }

      if (!failuresPath) {
        failuresPath = path.join(
          repoRoot,
          "subjects",
          "datasets",
          npcKey,
          technique,
          "quality_failures.json",
        );
      }

      if (
        !failuresPath.startsWith(
          path.join(repoRoot, "subjects", "datasets"),
        )
      ) {
        res.status(400).json({ error: "Invalid path" });
        return;
      }
      if (!fs.existsSync(failuresPath)) {
        res.status(404).json({
          error: `Quality failures not found for ${npcKey}/${technique}`,
        });
        return;
      }

      try {
        const failures = JSON.parse(fs.readFileSync(failuresPath, "utf8"));
        res.json(failures);
      } catch {
        res.status(500).json({ error: "Failed to load quality failures" });
      }
    },
  );

  // ── GET /api/dataset/:npcKey/:technique ───────────────────────────
  app.get(
    "/api/dataset/:npcKey/:technique",
    (req: Request, res: Response) => {
      const { npcKey, technique } = req.params;
      const n = Math.min(
        Math.max(
          parseInt(String(req.query.n || "10"), 10) || 10,
          1,
        ),
        100,
      );

      if (npcKey.includes("..") || technique.includes("..")) {
        res.status(400).json({ error: "Invalid path" });
        return;
      }

      const trainPath = path.join(
        repoRoot,
        "subjects",
        "datasets",
        npcKey,
        technique,
        "train.jsonl",
      );
      if (!fs.existsSync(trainPath)) {
        res.status(404).json({
          error: `Dataset ${npcKey}/${technique} not found. Run generation first.`,
        });
        return;
      }

      try {
        const content = fs.readFileSync(trainPath, "utf8");
        const lines = content.split("\n").filter(Boolean);
        const total = lines.length;
        const samples = lines.slice(0, n).map((line, i) => {
          try {
            return JSON.parse(line);
          } catch {
            return {
              _parseError: true,
              _line: i,
              _raw: line.slice(0, 200),
            };
          }
        });

        res.json({
          npcKey,
          technique,
          total,
          samples,
          showing: Math.min(n, total),
        });
      } catch (err) {
        res
          .status(500)
          .json({
            error:
              err instanceof Error ? err.message : "Failed to read dataset",
          });
      }
    },
  );

  // ── Quality-related helper routes ─────────────────────────────────
  app.get(
    "/api/datasets/quality-summary",
    (_req: Request, res: Response) => {
      const datasetsDir = path.join(repoRoot, "subjects", "datasets");
      if (!fs.existsSync(datasetsDir)) {
        res.json([]);
        return;
      }
      try {
        const results: Array<{
          npcKey: string;
          technique: string;
          path: string;
          summary: Record<string, unknown>;
        }> = [];
        const npcDirs = fs.readdirSync(datasetsDir);
        for (const npcKey of npcDirs) {
          const npcDir = path.join(datasetsDir, npcKey);
          if (!fs.statSync(npcDir).isDirectory()) continue;
          const techniqueDirs = fs.readdirSync(npcDir);
          for (const technique of techniqueDirs) {
            const summaryPath = path.join(
              npcDir,
              technique,
              "quality_summary.json",
            );
            if (fs.existsSync(summaryPath)) {
              try {
                const summary = JSON.parse(
                  fs.readFileSync(summaryPath, "utf8"),
                );
                results.push({
                  npcKey,
                  technique,
                  path: `subjects/datasets/${npcKey}/${technique}/quality_summary.json`,
                  summary,
                });
              } catch {
                // skip malformed
              }
            }
          }
        }
        res.json(results);
      } catch (err) {
        res
          .status(500)
          .json({ error: "Failed to list quality summaries" });
      }
    },
  );
}
