import type { Express, Request, Response } from "express";
import type { RouterDependencies } from "../types";

/**
 * Confident AI AI Connection endpoint for NPC evaluation.
 * 
 * This endpoint allows Confident AI to connect to the dashboard and run evaluations
 * without writing code. Confident AI will call this endpoint with golden data and
 * expect the actual model output in response.
 */

interface ConfidentRequest {
  input: string;
  context?: string[];
  conversationalContext?: string[];
  turns?: Array<{ role: string; content: string }>;
  hyperparameters?: {
    npc_key?: string;
    technique?: string;
    [key: string]: unknown;
  };
  prompts?: Record<string, { alias: string; version: string }>;
}

interface ConfidentResponse {
  output: string;
  metadata?: {
    npc_key?: string;
    technique?: string;
    model_key?: string;
    [key: string]: unknown;
  };
}

export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot, globalLog } = deps;

  /**
   * POST /api/confident/generate
   * 
   * Main endpoint for Confident AI AI Connection.
   * Accepts golden data and returns NPC model output.
   */
  app.post("/api/confident/generate", async (req: Request, res: Response) => {
    try {
      const body = req.body as ConfidentRequest;

      // Extract parameters
      const input = body.input || "";
      const context = body.context || body.conversationalContext || [];
      const hyperparameters = body.hyperparameters || {};
      const npcKey = hyperparameters.npc_key || "history_guide";
      const technique = hyperparameters.technique || "ollama";

      globalLog(deps.registry, `[CONFIDENT] Generating response for ${npcKey} (${technique})`);

      // TODO: Actually load and use the trained NPC model
      // For now, return a mock response
      // In production, this would:
      // 1. Load the model from artifacts/models/{npc_key}/best
      // 2. Generate response using the model
      // 3. Return the actual output

      const mockOutput = `[Mock response from ${npcKey}]: ${input}`;

      const response: ConfidentResponse = {
        output: mockOutput,
        metadata: {
          npc_key: npcKey,
          technique: technique,
          model_key: `${npcKey}_${technique}`,
          timestamp: new Date().toISOString(),
        },
      };

      res.json(response);
    } catch (error) {
      globalLog(deps.registry, `[CONFIDENT] Error: ${error}`);
      res.status(500).json({
        error: "Generation failed",
        details: error instanceof Error ? error.message : String(error),
      });
    }
  });

  /**
   * POST /api/confident/npc/:npcKey/generate
   * 
   * NPC-specific endpoint for Confident AI AI Connection.
   */
  app.post("/api/confident/npc/:npcKey/generate", async (req: Request, res: Response) => {
    try {
      const { npcKey } = req.params;
      const body = req.body as ConfidentRequest;

      const input = body.input || "";
      const context = body.context || body.conversationalContext || [];
      const hyperparameters = body.hyperparameters || {};
      const technique = hyperparameters.technique || "ollama";

      globalLog(deps.registry, `[CONFIDENT] Generating response for ${npcKey} (${technique})`);

      // TODO: Load the specific NPC model and generate response
      const mockOutput = `[Mock response from ${npcKey}]: ${input}`;

      const response: ConfidentResponse = {
        output: mockOutput,
        metadata: {
          npc_key: npcKey,
          technique: technique,
          model_key: `${npcKey}_${technique}`,
          timestamp: new Date().toISOString(),
        },
      };

      res.json(response);
    } catch (error) {
      globalLog(deps.registry, `[CONFIDENT] Error: ${error}`);
      res.status(500).json({
        error: "Generation failed",
        details: error instanceof Error ? error.message : String(error),
      });
    }
  });

  /**
   * GET /api/confident/health
   * 
   * Health check endpoint for Confident AI AI Connection.
   */
  app.get("/api/confident/health", (_req: Request, res: Response) => {
    res.json({
      status: "healthy",
      service: "Unsloth NPC Server",
      version: "1.0.0",
      timestamp: new Date().toISOString(),
    });
  });

  /**
   * GET /api/confident/models
   * 
   * List available NPC models for Confident AI.
   */
  app.get("/api/confident/models", async (_req: Request, res: Response) => {
    try {
      const modelsDir = `${repoRoot}/artifacts/models`;

      // Check if models directory exists
      const fs = await import("fs");
      const path = await import("path");

      if (!fs.existsSync(modelsDir)) {
        res.json({ models: [] });
        return;
      }

      const models: Array<{
        npc_key: string;
        path: string;
        has_best: boolean;
        has_latest: boolean;
      }> = [];

      const npcDirs = fs.readdirSync(modelsDir);
      for (const npcDir of npcDirs) {
        const npcPath = path.join(modelsDir, npcDir);
        if (fs.statSync(npcPath).isDirectory()) {
          models.push({
            npc_key: npcDir,
            path: npcPath,
            has_best: fs.existsSync(path.join(npcPath, "best")),
            has_latest: fs.existsSync(path.join(npcPath, "latest")),
          });
        }
      }

      res.json({ models });
    } catch (error) {
      globalLog(deps.registry, `[CONFIDENT] Error listing models: ${error}`);
      res.status(500).json({
        error: "Failed to list models",
        details: error instanceof Error ? error.message : String(error),
      });
    }
  });
}
