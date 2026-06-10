import type { Express, Request, Response } from "express";
import type { RouterDependencies } from "../types";
import fs from "node:fs";
import path from "node:path";

/**
 * Confident AI AI Connection endpoint for NPC evaluation.
 *
 * This endpoint allows Confident AI to connect to the dashboard and run evaluations
 * without writing code. Confident AI calls this endpoint with golden data and
 * expects the actual model output in response.
 *
 * Inference uses llama.cpp (via ~/llama-servers.sh on port 18080) instead of
 * Ollama — gives finer control over GPU layers, context sizing, and resource
 * usage on the local 6GB RTX 3060.
 *
 * Endpoint format matches what Confident AI expects for AI Connections:
 *   POST /api/confident/generate  ->  { output: "...", metadata: {...} }
 */

interface ConfidentRequest {
  input: string;
  context?: string[];
  conversationalContext?: string[];
  turns?: Array<{ role: string; content: string }>;
  hyperparameters?: {
    npc_key?: string;
    technique?: string;
    model?: string;
    temperature?: number;
    max_tokens?: number;
    gpu_layers?: number;
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
    model_used?: string;
    gpu_layers?: number;
    timestamp?: string;
    [key: string]: unknown;
  };
}

/** Load the NPC spec JSON and extract the system prompt. */
function loadNpcSystemPrompt(repoRoot: string, npcKey: string): string | null {
  const specPath = path.join(repoRoot, "data", "npcs", "specs", `${npcKey}.json`);
  try {
    if (!fs.existsSync(specPath)) return null;
    const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
    return spec.system_prompt || null;
  } catch {
    return null;
  }
}

/**
 * Call llama.cpp's OpenAI-compatible endpoint and return the response text.
 * Default port 18080 matches ~/llama-servers.sh chat server.
 * Override via LLAMA_CHAT_URL env var.
 */
async function callLlamaCpp(
  baseUrl: string,
  systemPrompt: string,
  userInput: string,
  temperature = 0.7,
  maxTokens = 512,
  gpuLayers = 24,
): Promise<string> {
  const url = `${baseUrl.replace(/\/+$/, "")}/v1/chat/completions`;

  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userInput },
      ],
      temperature,
      max_tokens: maxTokens,
      stream: false,
      // llama.cpp-specific inference params passed via top-level fields
      // (llama.cpp supports these when compiled with appropriate backends)
      n_gpu_layers: gpuLayers,
    }),
  });

  if (!response.ok) {
    const errorBody = await response.text().catch(() => "");
    throw new Error(`llama.cpp API error (${response.status}): ${errorBody}`);
  }

  const payload = (await response.json()) as {
    choices?: Array<{ message?: { content?: string } }>;
  };
  const content = payload.choices?.[0]?.message?.content || "";
  if (!content.trim()) throw new Error("llama.cpp returned empty response");
  return content;
}

export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const { repoRoot, globalLog } = deps;

  /**
   * GET /api/confident/health
   *
   * Health check endpoint for Confident AI AI Connection.
   */
  app.get("/api/confident/health", (_req: Request, res: Response) => {
    res.json({
      status: "healthy",
      service: "Unsloth NPC Server (llama.cpp)",
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
      const modelsDir = path.join(repoRoot, "artifacts", "models");

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
      res.status(500).json({
        error: "Failed to list models",
        details: error instanceof Error ? error.message : String(error),
      });
    }
  });

  /**
   * POST /api/confident/generate
   *
   * Main endpoint for Confident AI AI Connection.
   * Loads the NPC spec's system prompt and generates output via llama.cpp.
   */
  app.post("/api/confident/generate", async (req: Request, res: Response) => {
    try {
      const body = req.body as ConfidentRequest;

      const input = body.input || "";
      const hyperparameters = body.hyperparameters || {};
      const npcKey = hyperparameters.npc_key || "history_guide";

      // Config — defaults match ~/llama-servers.sh chat port
      const llamaBaseUrl =
        process.env.LLAMA_CHAT_URL || "http://127.0.0.1:18080";
      const temperature = hyperparameters.temperature ?? 0.7;
      const maxTokens = hyperparameters.max_tokens ?? 512;
      const gpuLayers = hyperparameters.gpu_layers ?? 24;

      globalLog(
        deps.registry,
        `[CONFIDENT] Generating for ${npcKey} via llama.cpp (GPU layers=${gpuLayers})`,
      );

      // Load the NPC system prompt
      const systemPrompt = loadNpcSystemPrompt(repoRoot, npcKey);
      if (!systemPrompt) {
        res.status(400).json({
          error: `NPC spec not found for '${npcKey}'`,
          details: `Expected at data/npcs/specs/${npcKey}.json`,
        });
        return;
      }

      // Generate output via llama.cpp
      let output: string;
      try {
        output = await callLlamaCpp(
          llamaBaseUrl,
          systemPrompt,
          input,
          temperature,
          maxTokens,
          gpuLayers,
        );
      } catch (llamaError) {
        globalLog(
          deps.registry,
          `[CONFIDENT] llama.cpp error for ${npcKey}: ${llamaError instanceof Error ? llamaError.message : String(llamaError)}`,
        );
        res.status(502).json({
          error: "llama.cpp generation failed",
          details:
            llamaError instanceof Error ? llamaError.message : String(llamaError),
          hint:
            `Ensure llama.cpp server is running on ${llamaBaseUrl}. ` +
            `Start with: ~/llama-servers.sh start`,
        });
        return;
      }

      const response: ConfidentResponse = {
        output,
        metadata: {
          npc_key: npcKey,
          model_used: "llama.cpp (GGUF)",
          gpu_layers: gpuLayers,
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
  app.post(
    "/api/confident/npc/:npcKey/generate",
    async (req: Request, res: Response) => {
      try {
        const { npcKey } = req.params;
        const body = req.body as ConfidentRequest;

        // Merge params into hyperparameters for consistent handling
        body.hyperparameters = { ...body.hyperparameters, npc_key: npcKey };

        const input = body.input || "";
        const hyperparameters = body.hyperparameters || {};
        const llamaBaseUrl =
          process.env.LLAMA_CHAT_URL || "http://127.0.0.1:18080";
        const temperature = hyperparameters.temperature ?? 0.7;
        const maxTokens = hyperparameters.max_tokens ?? 512;
        const gpuLayers = hyperparameters.gpu_layers ?? 24;

        globalLog(
          deps.registry,
          `[CONFIDENT] Generating for ${npcKey} via llama.cpp (GPU layers=${gpuLayers})`,
        );

        const systemPrompt = loadNpcSystemPrompt(repoRoot, npcKey);
        if (!systemPrompt) {
          res.status(400).json({
            error: `NPC spec not found for '${npcKey}'`,
            details: `Expected at data/npcs/specs/${npcKey}.json`,
          });
          return;
        }

        let output: string;
        try {
          output = await callLlamaCpp(
            llamaBaseUrl,
            systemPrompt,
            input,
            temperature,
            maxTokens,
            gpuLayers,
          );
        } catch (llamaError) {
          globalLog(
            deps.registry,
            `[CONFIDENT] llama.cpp error for ${npcKey}: ${llamaError instanceof Error ? llamaError.message : String(llamaError)}`,
          );
          res.status(502).json({
            error: "llama.cpp generation failed",
            details:
              llamaError instanceof Error
                ? llamaError.message
                : String(llamaError),
            hint:
              `Ensure llama.cpp server is running on ${llamaBaseUrl}. ` +
              `Start with: ~/llama-servers.sh start`,
          });
          return;
        }

        const response: ConfidentResponse = {
          output,
          metadata: {
            npc_key: npcKey,
            model_used: "llama.cpp (GGUF)",
            gpu_layers: gpuLayers,
            timestamp: new Date().toISOString(),
          },
        };

        res.json(response);
      } catch (error) {
        res.status(500).json({
          error: "Generation failed",
          details: error instanceof Error ? error.message : String(error),
        });
      }
    },
  );
}
