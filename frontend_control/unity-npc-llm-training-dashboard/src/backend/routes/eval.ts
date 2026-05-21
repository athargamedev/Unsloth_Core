import type { Express, Request, Response } from "express";
import path from "path";
import fs from "fs";
import type { RouterDependencies } from "../types";

/**
 * Registers /api/eval-reports/* and /api/feedback* routes.
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot } = deps;

  // ── GET /api/eval-reports ──────────────────────────────────────────────
  app.get("/api/eval-reports", (_req: Request, res: Response) => {
    const evalRoot = path.join(repoRoot, "eval");
    const reports: Array<{
      npcKey: string;
      files: Array<{ name: string; path: string }>;
    }> = [];
    const comparisons: Array<{ name: string; path: string }> = [];

    const reportsDir = path.join(evalRoot, "reports");
    if (fs.existsSync(reportsDir)) {
      for (const npcDir of fs.readdirSync(reportsDir)) {
        const npcPath = path.join(reportsDir, npcDir);
        if (!fs.statSync(npcPath).isDirectory()) continue;
        const files = fs.readdirSync(npcPath).map((f) => ({
          name: f,
          path: `eval/reports/${npcDir}/${f}`,
        }));
        reports.push({ npcKey: npcDir, files });
      }
    }

    const resultsDir = path.join(evalRoot, "results");
    if (fs.existsSync(resultsDir)) {
      const resultFiles = fs
        .readdirSync(resultsDir)
        .filter((f) => f.endsWith(".html") || f.endsWith(".htm"))
        .map((f) => ({
          name: f,
          path: `eval/results/${f}`,
        }));
      if (resultFiles.length > 0) {
        reports.push({ npcKey: "comparison-reports", files: resultFiles });
      }
    }

    const compDir = path.join(evalRoot, "comparisons");
    if (fs.existsSync(compDir)) {
      for (const f of fs.readdirSync(compDir)) {
        const fPath = path.join(compDir, f);
        if (!fs.statSync(fPath).isFile()) continue;
        comparisons.push({ name: f, path: `eval/comparisons/${f}` });
      }
    }

    res.json({ reports, comparisons });
  });

  // ── GET /api/eval-reports/file ─────────────────────────────────────────
  app.get("/api/eval-reports/file", (req: Request, res: Response) => {
    const requestedPath = String(req.query.path || "");
    if (requestedPath.includes("..")) {
      res.status(400).json({ error: "Invalid report path." });
      return;
    }

    const allowed = [
      path.resolve(repoRoot, "eval", "reports") + path.sep,
      path.resolve(repoRoot, "eval", "results") + path.sep,
    ];
    const absolutePath = path.resolve(repoRoot, requestedPath);
    const isAllowed = allowed.some((prefix) => absolutePath.startsWith(prefix));
    if (!isAllowed) {
      res.status(400).json({
        error: "Report path is outside allowed eval directories.",
      });
      return;
    }
    if (!fs.existsSync(absolutePath) || !fs.statSync(absolutePath).isFile()) {
      res.status(404).json({ error: "Report file not found." });
      return;
    }

    res.sendFile(absolutePath);
  });

  // ── GET /api/pipeline-state ────────────────────────────────────────────
  app.get("/api/pipeline-state", (_req: Request, res: Response) => {
    const statePath = path.join(
      repoRoot,
      "eval",
      "results",
      "pipeline_state.json",
    );
    if (!fs.existsSync(statePath)) {
      res.json({});
      return;
    }
    try {
      const raw = fs.readFileSync(statePath, "utf8");
      res.json(JSON.parse(raw));
    } catch {
      res
        .status(500)
        .json({ error: "Failed to parse pipeline_state.json" });
    }
  });

  // ── GET /api/feedback-results ──────────────────────────────────────────
  app.get("/api/feedback-results", (_req: Request, res: Response) => {
    const feedbackDir = path.join(
      repoRoot,
      "eval",
      "results",
      "feedback",
    );
    if (!fs.existsSync(feedbackDir)) {
      res.json([]);
      return;
    }
    try {
      const files = fs
        .readdirSync(feedbackDir)
        .filter((f) => f.endsWith(".json"))
        .map((f) => ({
          name: f,
          path: `eval/results/feedback/${f}`,
          lastModified: fs.statSync(path.join(feedbackDir, f)).mtimeMs,
        }))
        .sort((a, b) => b.lastModified - a.lastModified);
      res.json(files);
    } catch {
      res
        .status(500)
        .json({ error: "Failed to list feedback results" });
    }
  });

  // ── GET /api/feedback-result/file ──────────────────────────────────────
  app.get("/api/feedback-result/file", (req: Request, res: Response) => {
    const requestedPath = String(req.query.path || "");
    if (
      !requestedPath.startsWith("eval/results/feedback/") ||
      requestedPath.includes("..")
    ) {
      res.status(400).json({ error: "Invalid feedback result path." });
      return;
    }
    const absolutePath = path.resolve(repoRoot, requestedPath);
    if (
      !fs.existsSync(absolutePath) ||
      !fs.statSync(absolutePath).isFile()
    ) {
      res
        .status(404)
        .json({ error: "Feedback result file not found." });
      return;
    }
    try {
      const raw = fs.readFileSync(absolutePath, "utf8");
      res.json(JSON.parse(raw));
    } catch {
      res
        .status(500)
        .json({ error: "Failed to parse feedback result file." });
    }
  });
}
