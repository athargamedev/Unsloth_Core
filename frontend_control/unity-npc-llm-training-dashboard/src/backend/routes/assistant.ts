import type { Express, Request, Response } from "express";
import type { RouterDependencies } from "../types";
import { runAssistantChat, setAssistantModelLoaded, loadAssistantProfile } from "../services/assistant-orchestrator";
import { getAssistantResourceState } from "../services/assistant-resource-guard";

/** Registers workflow assistant routes. */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { registry, repoRoot, globalLog } = deps;

  app.get("/api/assistant/status", (req: Request, res: Response) => {
    const profile = loadAssistantProfile(repoRoot, String(req.query.profile || "") || undefined);
    const resourceState = getAssistantResourceState(registry);
    res.json({
      ok: true,
      model: profile.model,
      profile,
      resourceState,
      mode: resourceState.canUseLlm ? "ready" : "paused",
    });
  });

  const chatHandler = async (req: Request, res: Response) => {
    try {
      const message = String(req.body?.message || "").trim();
      if (!message) {
        res.status(400).json({ error: "message is required" });
        return;
      }
      const result = await runAssistantChat(repoRoot, registry, {
        message,
        history: Array.isArray(req.body?.history) ? req.body.history : [],
        npcKey: typeof req.body?.npcKey === "string" ? req.body.npcKey : undefined,
        technique: typeof req.body?.technique === "string" ? req.body.technique : undefined,
        runId: typeof req.body?.runId === "string" ? req.body.runId : undefined,
        jobId: typeof req.body?.jobId === "string" ? req.body.jobId : undefined,
        profile: typeof req.body?.profile === "string" ? req.body.profile : undefined,
      });
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "assistant failed" });
    }
  };

  app.post("/api/assistant/chat", chatHandler);
  app.post("/api/assistant", chatHandler); // backward-compatible frontend alias

  app.post("/api/assistant/load", async (req: Request, res: Response) => {
    try {
      const resourceState = getAssistantResourceState(registry);
      if (!resourceState.canUseLlm) {
        res.status(409).json({ error: resourceState.blockedReason || "assistant model load is paused" });
        return;
      }
      const result = await setAssistantModelLoaded(repoRoot, true, typeof req.body?.profile === "string" ? req.body.profile : undefined);
      globalLog(registry, `[ASSISTANT] loaded ${result.model}`);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "assistant load failed" });
    }
  });

  app.post("/api/assistant/unload", async (req: Request, res: Response) => {
    try {
      const result = await setAssistantModelLoaded(repoRoot, false, typeof req.body?.profile === "string" ? req.body.profile : undefined);
      globalLog(registry, `[ASSISTANT] unloaded ${result.model}`);
      res.json(result);
    } catch (error) {
      res.status(500).json({ error: error instanceof Error ? error.message : "assistant unload failed" });
    }
  });

  app.post("/api/assistant/execute", (_req: Request, res: Response) => {
    res.status(403).json({
      error: "Direct assistant shell execution is disabled. Use proposed actions backed by /api/commands/start after explicit confirmation.",
    });
  });
}
