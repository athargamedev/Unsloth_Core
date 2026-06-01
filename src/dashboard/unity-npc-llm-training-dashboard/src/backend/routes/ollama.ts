import type { Express, Request, Response } from "express";
import fs from "fs";
import { execSync } from "child_process";
import type { RouterDependencies } from "../types";

const OLLAMA_SERVICE = "ollama";
const OLLAMA_API_BASE = "http://127.0.0.1:11434";
const OLLAMA_OVERRIDE_PATH = "/etc/systemd/system/ollama.service.d/override.conf";

/**
 * Registers /api/ollama/* routes.
 */
export function registerRoutes(app: Express, _deps: RouterDependencies): void {
  // ── Helpers ─────────────────────────────────────────────────────────────

  const safeExec = (cmd: string): string | null => {
    try {
      return execSync(cmd, { encoding: "utf8", timeout: 5000 }).trim();
    } catch {
      return null;
    }
  };

  const parseOverrideEnv = (lines: string[], key: string): string | null => {
    const re = new RegExp(`^Environment="?${key}\\s*=\\s*(.+?)"?$`);
    for (const line of lines) {
      const trimmed = line.trim();
      const match = trimmed.match(re);
      if (match) {
        let val = match[1].replace(/"$/, "");
        const commentIdx = val.indexOf("#");
        if (commentIdx >= 0) val = val.slice(0, commentIdx).trim();
        return val;
      }
    }
    return null;
  };

  const readOverrideLines = (): string[] => {
    try {
      if (fs.existsSync(OLLAMA_OVERRIDE_PATH)) {
        return fs.readFileSync(OLLAMA_OVERRIDE_PATH, "utf8").split("\n");
      }
    } catch {
      // not accessible
    }
    return [];
  };

  const ollamaApiFetch = async <T>(path: string): Promise<T | null> => {
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 2000);
      try {
        const response = await fetch(`${OLLAMA_API_BASE}${path}`, {
          signal: controller.signal,
        });
        if (!response.ok) return null;
        return (await response.json()) as T;
      } finally {
        clearTimeout(timeout);
      }
    } catch {
      return null;
    }
  };

  // ── GET /api/ollama/status ──────────────────────────────────────────────
  app.get("/api/ollama/status", async (_req: Request, res: Response) => {
    const isActive = safeExec("systemctl is-active ollama");
    const running = isActive === "active";

    let pid: number | undefined;
    if (running) {
      const pidStr = safeExec(
        "systemctl show --property=MainPID ollama",
      );
      if (pidStr) {
        const parsed = parseInt(
          pidStr.replace("MainPID=", ""),
          10,
        );
        if (Number.isFinite(parsed) && parsed > 0) pid = parsed;
      }
    }

    const overrideLines = readOverrideLines();
    const defaults = {
      OLLAMA_NUM_PARALLEL:
        parseOverrideEnv(overrideLines, "OLLAMA_NUM_PARALLEL") || "1",
      OLLAMA_FLASH_ATTENTION:
        parseOverrideEnv(overrideLines, "OLLAMA_FLASH_ATTENTION") || "0",
      OLLAMA_KV_CACHE_TYPE:
        parseOverrideEnv(overrideLines, "OLLAMA_KV_CACHE_TYPE") || "f16",
      num_gpu: "999",
    };

    let activeModel: string | null = null;
    let gpuLayers: number | null = null;
    if (running) {
      const psData = await ollamaApiFetch<{
        models?: Array<{
          name?: string;
          model?: string;
          details?: Record<string, unknown>;
        }>;
      }>("/api/ps");
      if (psData?.models?.length) {
        activeModel =
          psData.models[0].model || psData.models[0].name || null;
        const details = psData.models[0].details;
        if (details?.gpu_layers != null) {
          gpuLayers = Number(details.gpu_layers);
        }
      }
    }

    if (running && activeModel) {
      const modelName = activeModel.split(":")[0];
      // Validate model name to prevent shell injection into `ollama show`.
      if (!/^[a-zA-Z0-9_.-]+$/.test(modelName)) {
        defaults.num_gpu = "999";
      } else {
        const showInfo = safeExec(
          `ollama show ${modelName} 2>/dev/null || true`,
        );
        if (showInfo) {
          for (const line of showInfo.split("\n")) {
            if (line.includes("num_gpu")) {
              const match = line.match(/num_gpu\s+(\d+)/);
              if (match) defaults.num_gpu = match[1];
              break;
            }
          }
        }
      }
    }

    res.json({
      running,
      pid,
      config: defaults,
      activeModel,
      gpuLayers,
    });
  });

  // ── GET /api/ollama/models ──────────────────────────────────────────────
  app.get("/api/ollama/models", async (_req: Request, res: Response) => {
    const tagsData = await ollamaApiFetch<{
      models?: Array<{
        name: string;
        size?: number;
        modified_at?: string;
        details?: {
          parameter_size?: string;
          quantization_level?: string;
          family?: string;
        };
      }>;
    }>("/api/tags");

    if (tagsData?.models) {
      const models = tagsData.models.map((m) => ({
        name: m.name,
        size: String(m.size ?? 0),
        modified: m.modified_at || "",
        details: m.details,
      }));
      res.json({ models });
      return;
    }

    // Fallback parse
    const listOut = safeExec("ollama list 2>/dev/null");
    if (listOut) {
      const lines = listOut.trim().split("\n").slice(1);
      const models = lines
        .filter((l) => l.trim())
        .map((l) => {
          const parts = l.split(/\s{2,}/);
          return {
            name: parts[0]?.trim() || "unknown",
            size: parts[2]?.trim() || "0",
            modified: parts[3]?.trim() || "",
          };
        });
      res.json({ models });
      return;
    }

    res.json({ models: [] });
  });

  // ── POST /api/ollama/apply-config ───────────────────────────────────────
  app.post("/api/ollama/apply-config", (req: Request, res: Response) => {
    const body = req.body as {
      OLLAMA_NUM_PARALLEL?: number;
      OLLAMA_FLASH_ATTENTION?: boolean;
      OLLAMA_KV_CACHE_TYPE?: string;
      num_gpu?: number;
      restart?: boolean;
    };

    const overrideLines = readOverrideLines();
    const currentEnv: Record<string, string> = {
      OLLAMA_NUM_PARALLEL:
        parseOverrideEnv(overrideLines, "OLLAMA_NUM_PARALLEL") || "1",
      OLLAMA_FLASH_ATTENTION:
        parseOverrideEnv(overrideLines, "OLLAMA_FLASH_ATTENTION") || "0",
      OLLAMA_KV_CACHE_TYPE:
        parseOverrideEnv(overrideLines, "OLLAMA_KV_CACHE_TYPE") || "f16",
    };

    const newEnv: Record<string, string> = { ...currentEnv };
    if (body.OLLAMA_NUM_PARALLEL !== undefined) {
      const val = Math.max(
        1,
        Math.min(8, Math.round(body.OLLAMA_NUM_PARALLEL)),
      );
      newEnv.OLLAMA_NUM_PARALLEL = String(val);
    }
    if (body.OLLAMA_FLASH_ATTENTION !== undefined) {
      newEnv.OLLAMA_FLASH_ATTENTION = body.OLLAMA_FLASH_ATTENTION
        ? "1"
        : "0";
    }
    if (body.OLLAMA_KV_CACHE_TYPE !== undefined) {
      const valid = ["f16", "q8_0", "q4_0"];
      if (valid.includes(body.OLLAMA_KV_CACHE_TYPE)) {
        newEnv.OLLAMA_KV_CACHE_TYPE = body.OLLAMA_KV_CACHE_TYPE;
      }
    }

    const lines: string[] = ["[Service]"];
    for (const [key, val] of Object.entries(newEnv)) {
      lines.push(`Environment="${key}=${val}"`);
    }

    try {
      const overrideDir = require("path").dirname(
        OLLAMA_OVERRIDE_PATH,
      );
      if (!fs.existsSync(overrideDir)) {
        fs.mkdirSync(overrideDir, { recursive: true });
      }
      fs.writeFileSync(
        OLLAMA_OVERRIDE_PATH,
        lines.join("\n") + "\n",
        "utf8",
      );

      const reloadResult = safeExec("systemctl daemon-reload");
      const needsRestart = true;

      if (reloadResult === null) {
        res.status(403).json({
          success: false,
          needsRestart: false,
          message:
            "Permission denied: cannot reload systemd. Try running with sudo.",
        });
        return;
      }

      if (body.restart) {
        const restartResult = safeExec("systemctl restart ollama");
        if (restartResult === null) {
          res.status(403).json({
            success: false,
            needsRestart: true,
            message:
              "Config written but restart failed — may need sudo.",
          });
          return;
        }
        res.json({
          success: true,
          needsRestart: false,
          message: "Config applied and Ollama restarted successfully.",
        });
        return;
      }

      res.json({
        success: true,
        needsRestart,
        message: "Config saved. Restart Ollama for changes to take effect.",
      });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to apply config";
      res.status(500).json({
        success: false,
        needsRestart: false,
        message,
      });
    }
  });

  // ── POST /api/ollama/restart ────────────────────────────────────────────
  app.post("/api/ollama/restart", (_req: Request, res: Response) => {
    const result = safeExec("systemctl restart ollama");
    if (result === null) {
      const retry = safeExec("/usr/bin/systemctl restart ollama");
      if (retry === null) {
        res.status(403).json({
          success: false,
          message:
            "Failed to restart Ollama. Try: sudo systemctl restart ollama",
        });
        return;
      }
    }
    res.json({
      success: true,
      message: "Ollama service restarted",
    });
  });
}
