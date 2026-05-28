import path from "node:path";
import fs from "node:fs";
import type { Express, Request, Response } from "express";
import type { RouterDependencies, StartCommandPayload, Job } from "../types";
import { launchJob, stopJob, updateStagesFromTruth, makeId, isoNow } from "../services/job-runner";
import { validateRequiredFields } from "../lib/validation";

/**
 * Registers /api/commands/* endpoints.
 *
 * GET  /api/available-commands  — list command definitions (without `build`)
 * GET  /api/command-schemas     — schemas with {npcKey} resolved defaults
 * POST /api/commands/start      — start a command as a new job
 * POST /api/commands/stop       — stop a running job by id
 */
export function registerRoutes(app: Express, deps: RouterDependencies): void {
  const {
    registry,
    commandMap,
    runningProcesses,
    terminalJobState,
    stopEscalationTimers,
    broadcast,
    globalLog,
    persistRegistry,
    flushPersist,
    invalidateJobsCache,
    repoRoot,
    unloadGemmaModel,
  } = deps;

  // ── GET /api/available-commands ─────────────────────────────────────────
  app.get("/api/available-commands", (_req: Request, res: Response) => {
    const defs = Array.from(commandMap.values()).map(
      ({ build, ...rest }) => rest,
    );
    res.json(defs);
  });

  // ── GET /api/command-schemas ────────────────────────────────────────────
  app.get("/api/command-schemas", (req: Request, res: Response) => {
    const npcKey =
      String(req.query.npcKey || "history_guide").trim() ||
      "history_guide";

    type FieldSchema = {
      type: "string" | "number" | "boolean";
      required: boolean;
      default?: string | number | boolean;
      description?: string;
      enum?: string[];
    };

    const DEFAULT_BASE_MODEL =
      process.env.DEFAULT_BASE_MODEL ||
      "unsloth/Llama-3.2-3B-Instruct-bnb-4bit";

    // Load presets for enum options
    const presetsDir = path.join(
      repoRoot,
      "configs",
      "presets",
    );
    const presetOptions: string[] = [];
    try {
      if (fs.existsSync(presetsDir)) {
        for (const file of fs.readdirSync(presetsDir)) {
          if (
            !(
              file.endsWith(".yaml") || file.endsWith(".yml")
            )
          )
            continue;
          presetOptions.push(
            file.replace(/\.ya?ml$/, ""),
          );
        }
      }
    } catch {
      // presets dir may not exist
    }

    // Preset enums from CLI help
    const judgePresetOptions = ["judge-qwen25", "judge-llama31-exp", "judge-qwen35-exp", "judge-qwen3-exp"];
    const generationPresetOptions = ["generate-qwen25", "generate-llama31", "generate-qwen35-exp", "generate-qwen3-exp"];
    const artifactCheckOptions = ["strict", "warn", "off"];
    const displayOptions = ["all", "failing", "passing"];
    const outtypeOptions = ["f32", "f16", "bf16", "q8_0"];
    const formatOptions = ["yaml", "json"];
    const schedulerOptions = ["cosine", "linear", "constant"];

    const baseDefaultsByCommand: Record<
      string,
      Record<string, FieldSchema>
    > = {
      // ── Generate ─────────────────────────────────────────────────────────
      "dataset-generate": {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec path",
        },
        "options.technique": {
          type: "string",
          required: false,
          default: "template",
          enum: ["template", "docs", "ollama", "openai", "anthropic"],
          description: "Dataset generation technique",
        },
        "options.modelId": {
          type: "string",
          required: false,
          default: "",
          description: "HF model override for generation",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Workflow hooks JSONL path",
        },
      },

      // ── Generate-Ollama ──────────────────────────────────────────────────
      "generate-ollama": {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec path",
        },
        "options.model": {
          type: "string",
          required: false,
          default: "llama3.1-3060-chat:latest",
          description: "Ollama model name",
        },
        "options.url": {
          type: "string",
          required: false,
          default: "http://localhost:11434",
          description: "Ollama server URL",
        },
        "options.batchSize": {
          type: "number",
          required: false,
          default: 4,
          description: "Concurrent generation tasks",
        },
        "options.maxRetries": {
          type: "number",
          required: false,
          default: 3,
          description: "Max retries per generation",
        },
        "options.temperature": {
          type: "number",
          required: false,
          default: 0.6,
          description: "Generation temperature",
        },
        "options.multiTurnRatio": {
          type: "number",
          required: false,
          default: 0.25,
          description: "Fraction of two-turn dialogues",
        },
        "options.seed": {
          type: "number",
          required: false,
          default: 42,
          description: "Random seed",
        },
        "options.output": {
          type: "string",
          required: false,
          default: "",
          description: "Output JSONL path",
        },
        "options.noValidation": {
          type: "boolean",
          required: false,
          default: false,
          description: "Skip validation split",
        },
        "options.valSplit": {
          type: "number",
          required: false,
          default: 0.1,
          description: "Validation split ratio",
        },
        "options.checkHealth": {
          type: "boolean",
          required: false,
          default: false,
          description: "Verify Ollama is running",
        },
        "options.pullModel": {
          type: "boolean",
          required: false,
          default: false,
          description: "Auto-pull model if not found",
        },
        "options.conceptFocus": {
          type: "string",
          required: false,
          default: "",
          description: "Focus on specific categories (comma-separated)",
        },
        "options.dryRun": {
          type: "boolean",
          required: false,
          default: false,
          description: "Show plan without generating",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Workflow hooks JSONL path",
        },
      },

      // ── Train ────────────────────────────────────────────────────────────
      train: {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec path (--from-spec mode)",
        },
        preset: {
          type: "string",
          required: false,
          default: "fast-3b",
          enum: presetOptions.length ? presetOptions : undefined,
          description: "Training preset",
        },
        "options.technique": {
          type: "string",
          required: false,
          default: "template",
          enum: ["template", "docs", "ollama", "openai", "anthropic"],
          description: "Dataset technique",
        },
        "options.modelId": {
          type: "string",
          required: false,
          default: DEFAULT_BASE_MODEL,
          description: "HF model ID (e.g., unsloth/Qwen3-1.7B-bnb-4bit)",
        },
        "options.exportGguf": {
          type: "boolean",
          required: false,
          default: false,
          description: "Export adapter GGUF after training",
        },
        "options.fullMergeExport": {
          type: "boolean",
          required: false,
          default: false,
          description: "Full merge GGUF export (standalone)",
        },
        "options.wandb": {
          type: "boolean",
          required: false,
          default: false,
          description: "Enable W&B logging",
        },
        "options.learningRate": {
          type: "string",
          required: false,
          default: "2e-4",
          description: "Learning rate",
        },
        "options.batchSize": {
          type: "number",
          required: false,
          default: 1,
          description: "Batch size",
        },
        "options.epochs": {
          type: "number",
          required: false,
          default: 3,
          description: "Number of epochs",
        },
        "options.rank": {
          type: "number",
          required: false,
          default: 16,
          description: "LoRA rank",
        },
        "options.alpha": {
          type: "number",
          required: false,
          default: 32,
          description: "LoRA alpha",
        },
        "options.scheduler": {
          type: "string",
          required: false,
          default: "cosine",
          enum: schedulerOptions,
          description: "LR scheduler type",
        },
        "options.modelPreset": {
          type: "string",
          required: false,
          default: "",
          description: "Named model preset",
        },
        "options.datasetEvalSkip": {
          type: "boolean",
          required: false,
          default: false,
          description: "Skip dataset evaluation gate",
        },
        "options.datasetEvalJudgeModel": {
          type: "string",
          required: false,
          default: "",
          description: "Dataset eval judge model (Ollama)",
        },
        "options.datasetEvalJudgePreset": {
          type: "string",
          required: false,
          default: "",
          enum: judgePresetOptions,
          description: "Dataset eval judge preset",
        },
        "options.deepevalSoftFail": {
          type: "boolean",
          required: false,
          default: false,
          description: "Continue on dataset eval metric failures",
        },
        "options.deepevalOllamaUrl": {
          type: "string",
          required: false,
          default: "http://localhost:11434",
          description: "Ollama URL for DeepEval",
        },
        "options.deepevalCasesPerCategory": {
          type: "number",
          required: false,
          default: 1,
          description: "DeepEval cases per category",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Workflow hooks JSONL path",
        },
      },

      // ── Evaluate ─────────────────────────────────────────────────────────
      evaluate: {
        spec: {
          type: "string",
          required: false,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec path",
        },
        "options.model": {
          type: "string",
          required: false,
          default: "",
          description: "Single model GGUF path (alternative to baseline/candidate)",
        },
        "options.baseline": {
          type: "string",
          required: false,
          default: "exports/{npcKey}/{npcKey}-lora-f16.gguf",
          description: "Baseline GGUF model path",
        },
        "options.candidate": {
          type: "string",
          required: false,
          default: "",
          description: "Candidate GGUF model path",
        },
        "options.valData": {
          type: "string",
          required: false,
          default: "",
          description: "Validation JSONL path",
        },
        "options.numQuestions": {
          type: "number",
          required: false,
          default: 5,
          description: "Number of eval questions",
        },
        "options.output": {
          type: "string",
          required: false,
          default: "",
          description: "Output report path",
        },
        "options.reportHtml": {
          type: "boolean",
          required: false,
          default: false,
          description: "Generate HTML report with charts",
        },
        "options.judge": {
          type: "boolean",
          required: false,
          default: false,
          description: "Use local Ollama judge",
        },
        "options.judgeModel": {
          type: "string",
          required: false,
          default: "qwen3:latest",
          description: "Judge model (Ollama)",
        },
        "options.track": {
          type: "boolean",
          required: false,
          default: false,
          description: "Track results in eval/results/",
        },
        "options.wandb": {
          type: "boolean",
          required: false,
          default: false,
          description: "Enable W&B evaluation tracking",
        },
        "options.wandbProject": {
          type: "string",
          required: false,
          default: "unsloth-core",
          description: "W&B project",
        },
        "options.wandbEntity": {
          type: "string",
          required: false,
          default: "",
          description: "W&B entity (auto-detect if empty)",
        },
        "options.interactive": {
          type: "boolean",
          required: false,
          default: false,
          description: "Interactive chat mode",
        },
        "options.host": {
          type: "string",
          required: false,
          default: "127.0.0.1",
          description: "llama-server host",
        },
        "options.port": {
          type: "number",
          required: false,
          default: 8888,
          description: "llama-server port",
        },
        "options.gpuLayers": {
          type: "number",
          required: false,
          default: 99,
          description: "GPU layers to offload (0 = CPU-only)",
        },
        "options.maxTokens": {
          type: "number",
          required: false,
          default: 256,
          description: "Max tokens per eval answer",
        },
        "options.feedbackJson": {
          type: "string",
          required: false,
          default: "",
          description: "Save per-concept feedback JSON",
        },
        "options.baseModel": {
          type: "string",
          required: false,
          default: "",
          description: "Base GGUF path (for LoRA adapter evaluation)",
        },
        "options.loraWeight": {
          type: "number",
          required: false,
          default: 1.0,
          description: "LoRA adapter weight",
        },
        "options.trainingMetrics": {
          type: "string",
          required: false,
          default: "",
          description: "Show TensorBoard metrics (optional: runs dir path, 'true' for default)",
        },
        "options.npcKey": {
          type: "string",
          required: false,
          default: "",
          description: "NPC key for TensorBoard lookup",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Workflow hooks JSONL path",
        },
      },

      // ── Feedback ─────────────────────────────────────────────────────────
      feedback: {
        "options.feedbackJson": {
          type: "string",
          required: false,
          default: "",
          description: "Path to feedback JSON from evaluate --feedback-json",
        },
        spec: {
          type: "string",
          required: false,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec (alternative mode without feedback_json)",
        },
        "options.candidate": {
          type: "string",
          required: false,
          default: "",
          description: "Candidate GGUF (alternative mode)",
        },
        "options.winRateThreshold": {
          type: "number",
          required: false,
          default: 0.5,
          description: "Minimum win rate threshold",
        },
        "options.qualityThreshold": {
          type: "number",
          required: false,
          default: 25.0,
          description: "Maximum quality score (lower=better)",
        },
        "options.violationThreshold": {
          type: "number",
          required: false,
          default: 1,
          description: "Max constraint violations",
        },
        "options.dryRun": {
          type: "boolean",
          required: false,
          default: false,
          description: "Analyze without regenerating",
        },
        "options.auto": {
          type: "boolean",
          required: false,
          default: false,
          description: "Auto-accept all suggestions",
        },
        "options.skipGapDetection": {
          type: "boolean",
          required: false,
          default: false,
          description: "Skip knowledge coverage check",
        },
        "options.saveGaps": {
          type: "string",
          required: false,
          default: "",
          description: "Save gap report to JSON path",
        },
        "options.json": {
          type: "boolean",
          required: false,
          default: false,
          description: "Output machine-readable JSON",
        },
        "options.autoRetrain": {
          type: "boolean",
          required: false,
          default: false,
          description: "Auto-retrain and re-evaluate after regeneration",
        },
        "options.trainPreset": {
          type: "string",
          required: false,
          default: "fast-3b",
          enum: presetOptions.length ? presetOptions : undefined,
          description: "Training preset for auto-retrain",
        },
        "options.baseline": {
          type: "string",
          required: false,
          default: "",
          description: "Baseline GGUF for auto-evaluation",
        },
        "options.regenerationTechnique": {
          type: "string",
          required: false,
          default: "template",
          enum: ["template", "ollama"],
          description: "Regeneration technique",
        },
        "options.regenerationPreset": {
          type: "string",
          required: false,
          default: "",
          enum: generationPresetOptions,
          description: "Named Ollama regeneration preset",
        },
        "options.deepevalJudgeModel": {
          type: "string",
          required: false,
          default: "",
          description: "DeepEval judge model",
        },
        "options.deepevalJudgePreset": {
          type: "string",
          required: false,
          default: "",
          enum: judgePresetOptions,
          description: "DeepEval judge preset",
        },
        "options.deepevalOllamaUrl": {
          type: "string",
          required: false,
          default: "http://localhost:11434",
          description: "Ollama URL for DeepEval",
        },
        "options.deepevalCasesPerCategory": {
          type: "number",
          required: false,
          default: 1,
          description: "DeepEval cases per category",
        },
        "options.deepevalSoftFail": {
          type: "boolean",
          required: false,
          default: false,
          description: "Continue on dataset eval failures",
        },
        "options.skipDatasetEval": {
          type: "boolean",
          required: false,
          default: false,
          description: "Skip dataset evaluation gate",
        },
        "options.regenerationModel": {
          type: "string",
          required: false,
          default: "",
          description: "Ollama model for regeneration",
        },
        "options.regenerationUrl": {
          type: "string",
          required: false,
          default: "",
          description: "Ollama URL for regeneration",
        },
        "options.regenerationBatchSize": {
          type: "number",
          required: false,
          default: 4,
          description: "Batch size for regeneration",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Workflow hooks JSONL path",
        },
      },

      // ── Sanitize ──────────────────────────────────────────────────────────
      "dataset-sanitize": {
        "options.datasetPath": {
          type: "string",
          required: true,
          default: "subjects/datasets/{npcKey}/template/train.jsonl",
          description: "Input dataset JSONL path",
        },
        "options.output": {
          type: "string",
          required: false,
          default: "",
          description: "Output JSONL path (defaults to *_clean.jsonl)",
        },
        "options.minLength": {
          type: "number",
          required: false,
          default: 10,
          description: "Min chars for assistant response",
        },
        "options.maxSentences": {
          type: "number",
          required: false,
          default: 5,
          description: "Max sentences for assistant response",
        },
        "options.verbose": {
          type: "boolean",
          required: false,
          default: false,
          description: "Print discarded examples and metadata warnings",
        },
        "options.spec": {
          type: "string",
          required: false,
          default: "",
          description: "Path to NPC spec JSON (better quality scoring)",
        },
        "options.strictCanonical": {
          type: "boolean",
          required: false,
          default: false,
          description: "Require canonical dataset path",
        },
        "options.strictMode": {
          type: "boolean",
          required: false,
          default: false,
          description: "Raise on structural validation errors instead of discarding",
        },
        "options.artifactCheck": {
          type: "string",
          required: false,
          default: "strict",
          enum: ["strict", "warn", "off"],
          description: "How to handle AI artifacts",
        },
        "options.verboseArtifacts": {
          type: "boolean",
          required: false,
          default: false,
          description: "Show the exact artifact pattern matched",
        },
        "options.qualityThresholdPass": {
          type: "number",
          required: false,
          default: 70,
          description: "Minimum total score to pass",
        },
        "options.qualityThresholdFlag": {
          type: "number",
          required: false,
          default: 50,
          description: "Below this total, examples are flagged for review",
        },
        "options.qualityReport": {
          type: "boolean",
          required: false,
          default: false,
          description: "Print quality score distribution at the end",
        },
        "options.discardBelowScore": {
          type: "number",
          required: false,
          default: 0,
          description: "Discard examples below this total score (0 = keep all)",
        },
        "options.noFixMetadata": {
          type: "boolean",
          required: false,
          default: false,
          description: "Disable auto-repair of missing metadata fields",
        },
        "options.requireCompleteMetadata": {
          type: "boolean",
          required: false,
          default: false,
          description: "Error out if any metadata field is missing",
        },
        "options.dedup": {
          type: "boolean",
          required: false,
          default: true,
          description: "Enable/disable content_hash deduplication",
        },
        "options.dedupReport": {
          type: "boolean",
          required: false,
          default: false,
          description: "Show which content hashes were removed during dedup",
        },
        "options.writeManifest": {
          type: "boolean",
          required: false,
          default: true,
          description: "Enable/disable enriched manifest writing",
        },
        "options.manifestPath": {
          type: "string",
          required: false,
          default: "",
          description: "Override manifest output path",
        },
        "options.debug": {
          type: "boolean",
          required: false,
          default: false,
          description: "Re-raise exceptions with traceback for debugging",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Path to a JSONL hook log for step tracing",
        },
      },
      "dataset-eval": {
        spec: {
          type: "string",
          required: true,
          default: "subjects/NPC_specs/{npcKey}.json",
          description: "Subject spec path",
        },
        "options.technique": {
          type: "string",
          required: false,
          default: "template",
          enum: ["template", "docs", "ollama", "openai", "anthropic"],
          description: "Dataset technique to evaluate",
        },
        "options.judgeModel": {
          type: "string",
          required: false,
          default: "",
          description: "Local Ollama judge model (auto-resolves from config if empty)",
        },
        "options.judgePreset": {
          type: "string",
          required: false,
          default: "",
          enum: ["", "judge-qwen25", "judge-llama31-exp", "judge-qwen35-exp", "judge-qwen3-exp"],
          description: "Named Ollama judge preset",
        },
        "options.ollamaBaseUrl": {
          type: "string",
          required: false,
          default: "http://localhost:11434",
          description: "Ollama server URL",
        },
        "options.judgeTemperature": {
          type: "number",
          required: false,
          default: 0.0,
          description: "Judge temperature",
        },
        "options.mode": {
          type: "string",
          required: false,
          default: "fast",
          enum: ["fast", "release"],
          description: "Dataset quality gate mode",
        },
        "options.casesPerCategory": {
          type: "number",
          required: false,
          default: 1,
          description: "Rows sampled per category",
        },
        "options.categories": {
          type: "string",
          required: false,
          default: "",
          description: "Comma-separated category filter",
        },
        "options.identifier": {
          type: "string",
          required: false,
          default: "",
          description: "DeepEval run identifier",
        },
        "options.display": {
          type: "string",
          required: false,
          default: "all",
          enum: ["all", "failing", "passing"],
          description: "DeepEval display mode",
        },
        "options.ignoreErrors": {
          type: "boolean",
          required: false,
          default: false,
          description: "Continue when individual metric calls error",
        },
        "options.softFail": {
          type: "boolean",
          required: false,
          default: false,
          description: "Write artifacts but return 0 even when metrics fail",
        },
        "options.output": {
          type: "string",
          required: false,
          default: "",
          description: "Quality summary JSON path",
        },
        "options.workflowHooks": {
          type: "string",
          required: false,
          default: "",
          description: "Path to a JSONL hook log for step tracing",
        },
      },
       pipeline: {
         spec: {
           type: "string",
           required: true,
           default: "subjects/NPC_specs/{npcKey}.json",
           description: "Subject spec path",
         },
         preset: {
           type: "string",
           required: false,
           default: "fast-3b",
           enum: presetOptions.length ? presetOptions : undefined,
           description: "Training preset",
         },
         "options.technique": {
           type: "string",
           required: false,
           default: "template",
           enum: ["template", "docs", "ollama", "openai", "anthropic"],
           description: "Dataset technique",
         },
         "options.track": {
           type: "boolean",
           required: false,
           default: false,
           description: "Track evaluation results",
         },
         "options.wandb": {
           type: "boolean",
           required: false,
           default: false,
           description: "Enable W&B logging",
         },
         "options.modelId": {
           type: "string",
           required: false,
           default: "",
           description: "HF model override",
         },
         "options.fullMergeExport": {
           type: "boolean",
           required: false,
           default: false,
           description: "Full merge GGUF export",
         },
         "options.skipSpecValidate": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip spec validation",
         },
         "options.skipDatasetEval": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip dataset quality gate",
         },
         "options.skipEval": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip model evaluation",
         },
         "options.skipSmoke": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip smoke test",
         },
         "options.numEvalQuestions": {
           type: "number",
           required: false,
           default: 5,
           description: "Number of evaluation questions",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Validate-Spec ─────────────────────────────────────────────────────
       "validate-spec": {
         spec: {
           type: "string",
           required: true,
           default: "subjects/NPC_specs/{npcKey}.json",
           description: "Subject spec path",
         },
         "options.all": {
           type: "boolean",
           required: false,
           default: false,
           description: "Validate all specs",
         },
         "options.json": {
           type: "boolean",
           required: false,
           default: false,
           description: "Output JSON",
         },
         "options.strict": {
           type: "boolean",
           required: false,
           default: false,
           description: "Treat warnings as errors",
         },
         "options.requireReferenceDocs": {
           type: "boolean",
           required: false,
           default: false,
           description: "Require reference docs",
         },
         "options.requireReferenceContract": {
           type: "boolean",
           required: false,
           default: false,
           description: "Require reference doc contract compliance",
         },
         "options.requireAllCategories": {
           type: "boolean",
           required: false,
           default: false,
           description: "Require all 5 dataset categories",
         },
         "options.requireDatasetMinimums": {
           type: "boolean",
           required: false,
           default: false,
           description: "Require minimum SFT counts per category",
         },
         "options.generationReady": {
           type: "boolean",
           required: false,
           default: true,
           description: "Full generation-ready validation",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Validate-Config ───────────────────────────────────────────────────
       "validate-config": {
         spec: {
           type: "string",
           required: true,
           default: "subjects/NPC_specs/{npcKey}.json",
           description: "Subject spec path",
         },
         "options.config": {
           type: "string",
           required: false,
           default: "",
           description: "Config YAML path",
         },
         preset: {
           type: "string",
           required: false,
           default: "fast-3b",
           enum: presetOptions.length ? presetOptions : undefined,
           description: "Training preset",
         },
         "options.dataPath": {
           type: "string",
           required: false,
           default: "",
           description: "Dataset path override",
         },
         "options.modelId": {
           type: "string",
           required: false,
           default: "",
           description: "Model ID override",
         },
         "options.output": {
           type: "string",
           required: false,
           default: "",
           description: "Output directory",
         },
         "options.npcKey": {
           type: "string",
           required: false,
           default: "",
           description: "NPC key for config-only mode",
         },
         "options.format": {
           type: "string",
           required: false,
           default: "yaml",
           enum: formatOptions,
           description: "Output format",
         },
         "options.strict": {
           type: "boolean",
           required: false,
           default: false,
           description: "Treat warnings as errors",
         },
         "options.requireCanonical": {
           type: "boolean",
           required: false,
           default: false,
           description: "Require canonical dataset path",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Export ────────────────────────────────────────────────────────────
       export: {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key",
         },
         "options.modelId": {
           type: "string",
           required: false,
           default: DEFAULT_BASE_MODEL,
           description: "Base HF model ID",
         },
         "options.quantization": {
           type: "string",
           required: false,
           default: "q4_k_m",
           description: "GGUF quantization (full-merge mode)",
         },
         "options.fullMerge": {
           type: "boolean",
           required: false,
           default: false,
           description: "Produce full merged GGUF",
         },
         "options.skipF16": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip f16 variant in full-merge mode",
         },
         "options.outtype": {
           type: "string",
           required: false,
           default: "f16",
           enum: outtypeOptions,
           description: "Adapter output format",
         },
         "options.maximumMemory": {
           type: "number",
           required: false,
           default: 0,
           description: "Max memory in GB for save_pretrained_gguf",
         },
         "options.resume": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip existing GGUFs",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Export-Resume ─────────────────────────────────────────────────────
       "export-resume": {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key",
         },
         "options.modelId": {
           type: "string",
           required: false,
           default: "",
           description: "Base model ID",
         },
         "options.quantization": {
           type: "string",
           required: false,
           default: "q4_k_m",
           description: "GGUF quantization",
         },
         "options.skipF16": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip f16 variants",
         },
         "options.timeoutSeconds": {
           type: "number",
           required: false,
           default: 0,
           description: "Timeout in seconds",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Export-Adapter ────────────────────────────────────────────────────
       "export-adapter": {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key (maps to outputs/{npcKey})",
         },
         "options.all": {
           type: "boolean",
           required: false,
           default: false,
           description: "Convert all adapters in outputs/",
         },
         "options.outtype": {
           type: "string",
           required: false,
           default: "f16",
           enum: ["f32", "f16", "bf16", "q8_0", "auto"],
           description: "Output format",
         },
         "options.outfile": {
           type: "string",
           required: false,
           default: "",
           description: "Explicit output file path",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Smoke ─────────────────────────────────────────────────────────────
       smoke: {
         spec: {
           type: "string",
           required: true,
           default: "subjects/NPC_specs/{npcKey}.json",
           description: "Subject spec path",
         },
         "options.modelPath": {
           type: "string",
           required: true,
           default: "exports/{npcKey}/{npcKey}-lora-f16.gguf",
           description: "GGUF model path",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Deploy ────────────────────────────────────────────────────────────
       deploy: {
         "options.unityProject": {
           type: "string",
           required: false,
           default: "",
           description: "Unity project path (auto-detected)",
         },
         "options.dryRun": {
           type: "boolean",
           required: false,
           default: false,
           description: "Show what would be done",
         },
         "options.skipExport": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip GGUF export step",
         },
         "options.exportOnly": {
           type: "boolean",
           required: false,
           default: false,
           description: "Only export, skip Unity copy",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Quick-Eval ────────────────────────────────────────────────────────
       "quick-eval": {
         "options.adapterPath": {
           type: "string",
           required: true,
           default: "exports/{npcKey}/{npcKey}-lora-f16.gguf",
           description: "Adapter GGUF path",
         },
         "options.samples": {
           type: "number",
           required: false,
           default: 5,
           description: "Number of samples",
         },
         spec: {
           type: "string",
           required: true,
           default: "subjects/NPC_specs/{npcKey}.json",
           description: "Subject spec path",
         },
         "options.valData": {
           type: "string",
           required: false,
           default: "",
           description: "Validation JSONL",
         },
         "options.output": {
           type: "string",
           required: false,
           default: "",
           description: "Output report path",
         },
         "options.feedbackJson": {
           type: "string",
           required: false,
           default: "",
           description: "Save per-concept feedback JSON",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Track ──────────────────────────────────────────────────────────────
       track: {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key",
         },
         "options.model": {
           type: "string",
           required: false,
           default: "",
           description: "Model path/ID",
         },
         "options.show": {
           type: "boolean",
           required: false,
           default: false,
           description: "Show tracked results",
         },
         "options.winRate": {
           type: "number",
           required: false,
           default: 0,
           description: "Win rate to record",
         },
         "options.avgQuality": {
           type: "number",
           required: false,
           default: 0,
           description: "Average quality score",
         },
         "options.valLoss": {
           type: "number",
           required: false,
           default: 0,
           description: "Validation loss",
         },
         "options.notes": {
           type: "string",
           required: false,
           default: "",
           description: "Notes",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Compare-Runs ───────────────────────────────────────────────────────
       "compare-runs": {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key",
         },
         "options.baselineRun": {
           type: "string",
           required: true,
           default: "",
           description: "Baseline run ID",
         },
         "options.candidateRun": {
           type: "string",
           required: true,
           default: "",
           description: "Candidate run ID",
         },
         "options.spec": {
           type: "string",
           required: false,
           default: "",
           description: "Subject spec path",
         },
         "options.numQuestions": {
           type: "number",
           required: false,
           default: 5,
           description: "Number of eval questions",
         },
         "options.judge": {
           type: "boolean",
           required: false,
           default: false,
           description: "Use Ollama judge",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Supabase-Check ────────────────────────────────────────────────────
       "supabase-check": {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key",
         },
         "options.playerId": {
           type: "string",
           required: false,
           default: "",
           description: "Player ID for memory check",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Audit ─────────────────────────────────────────────────────────────
       audit: {
         "options.full": {
           type: "boolean",
           required: false,
           default: false,
           description: "Full audit check",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Docs-Manifest-Generate ────────────────────────────────────────────
       "docs-manifest-generate": {
         spec: {
           type: "string",
           required: true,
           default: "subjects/NPC_specs/{npcKey}.json",
           description: "Subject spec path",
         },
         "options.manifest": {
           type: "string",
           required: false,
           default: "",
           description: "Docs manifest path",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Plan-Batch ─────────────────────────────────────────────────────────
       "plan-batch": {
         "options.specGlob": {
           type: "string",
           required: false,
           default: "subjects/NPC_specs/*.json",
           description: "Spec glob pattern",
         },
         "options.presets": {
           type: "string",
           required: false,
           default: "fast-3b,premium-3b,premium-8b,safe-any",
           description: "Presets to plan",
         },
         "options.localVram": {
           type: "number",
           required: false,
           default: 4.0,
           description: "Local VRAM in GB",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

       // ── Batch-Export ──────────────────────────────────────────────────────
       "batch-export": {
         "options.npc": {
           type: "string",
           required: false,
           default: "",
           description: "Comma-separated NPC keys (default: all)",
         },
         "options.quantization": {
           type: "string",
           required: false,
           default: "q4_k_m",
           description: "GGUF quantization",
         },
         "options.modelId": {
           type: "string",
           required: false,
           default: "",
           description: "Base model ID",
         },
         "options.skipF16": {
           type: "boolean",
           required: false,
           default: false,
           description: "Skip f16 variants",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },

        // ── Plan-Execution ──────────────────────────────────────────────────────
        "plan-execution": {
          spec: {
            type: "string",
            required: true,
            default: "subjects/NPC_specs/{npcKey}.json",
            description: "Subject spec path",
          },
          preset: {
            type: "string",
            required: false,
            default: "",
            description: "Training preset override",
          },
          "options.localVramGb": {
            type: "number",
            required: false,
            default: 0,
            description: "Override detected local VRAM (0 = auto-detect)",
          },
          "options.json": {
            type: "boolean",
            required: false,
            default: false,
            description: "Output JSON",
          },
          "options.workflowHooks": {
            type: "string",
            required: false,
            default: "",
            description: "Workflow hooks path",
          },
        },

        // ── TB-Reader ───────────────────────────────────────────────────────────
        "tb-reader": {
          "options.runDir": {
            type: "string",
            required: true,
            default: "",
            description: "Path to TensorBoard event directory",
          },
          "options.indent": {
            type: "number",
            required: false,
            default: 2,
            description: "JSON indent",
          },
          "options.workflowHooks": {
            type: "string",
            required: false,
            default: "",
            description: "Workflow hooks path",
          },
        },

        // ── Init ───────────────────────────────────────────────────────────────
        init: {
         npcKey: {
           type: "string",
           required: true,
           default: "{npcKey}",
           description: "NPC key (snake_case)",
         },
         "options.subject": {
           type: "string",
           required: false,
           default: "",
           description: "Subject description",
         },
         "options.name": {
           type: "string",
           required: false,
           default: "",
           description: "NPC display name",
         },
         "options.force": {
           type: "boolean",
           required: false,
           default: false,
           description: "Overwrite existing spec",
         },
         "options.skipSpec": {
           type: "boolean",
           required: false,
           default: false,
           description: "Only create folders, skip spec file",
         },
         "options.workflowHooks": {
           type: "string",
           required: false,
           default: "",
           description: "Workflow hooks path",
         },
       },
     };

    const schemas: Record<
      string,
      { fields: Record<string, FieldSchema> }
    > = {};

    for (const [id, def] of commandMap.entries()) {
      const fields: Record<string, FieldSchema> = {};

      for (const requiredField of def.requiredFields) {
        fields[requiredField] = {
          type: "string",
          required: true,
          description: `Required by ${id}`,
        };
      }

      const defaults = baseDefaultsByCommand[id] || {};
      for (const [k, v] of Object.entries(defaults)) {
        fields[k] = { ...fields[k], ...v };
      }

      fields.commandId = {
        type: "string",
        required: true,
        default: id,
        description: "Backend command identifier",
      };

      schemas[id] = { fields };
    }

    // Resolve {npcKey} templates
    const resolved = resolveTemplateDefaults(schemas, npcKey);
    res.json(resolved);
  });

  // ── POST /api/commands/start ────────────────────────────────────────────
  app.post("/api/commands/start", (req: Request, res: Response) => {
    try {
      const payload = req.body as StartCommandPayload;
      const commandDef = commandMap.get(payload.commandId || "");
      if (!commandDef) {
        res.status(400).json({ error: "Unknown commandId." });
        return;
      }
      if (registry.executionMode === "remote") {
        res.status(501).json({
          error: "Remote runner not implemented yet.",
          mode: "remote",
        });
        return;
      }

      validateRequiredFields(payload, commandDef.requiredFields);

      const command = commandDef.build(payload);
      const job: Job = {
        id: makeId(),
        name: `${commandDef.label}${payload.npcKey ? ` (${payload.npcKey})` : ""}`,
        type: payload.type || commandDef.type,
        commandId: commandDef.id,
        npcKey: payload.npcKey,
        status: "running",
        progress: 5,
        loss: null,
        createdAt: isoNow(),
        startedAt: isoNow(),
        command,
        stages: [
          { name: "Dataset Prep", status: "pending", logs: [] },
          { name: "Training", status: "pending", logs: [] },
          { name: "Evaluation", status: "pending", logs: [] },
          { name: "Export", status: "pending", logs: [] },
          { name: "Feedback", status: "pending", logs: [] },
        ],
        logs: [],
      };

      const startedJob = launchJob(job, {
        registry,
        repoRoot,
        broadcast,
        globalLog,
        persistRegistry,
        flushPersist,
        invalidateJobsCache,
        unloadGemmaModel,
        isoNow,
        makeId,
        defaultStages: () => [
          { name: "Dataset Prep", status: "pending" as const, logs: [] },
          { name: "Training", status: "pending" as const, logs: [] },
          { name: "Evaluation", status: "pending" as const, logs: [] },
          { name: "Export", status: "pending" as const, logs: [] },
          { name: "Feedback", status: "pending" as const, logs: [] },
        ],
        writeJobLog: (_jobId: string, _line: string) => {
          /* stub — replaced by full impl */
        },
      });
      res.json(startedJob);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to start command.";
      res.status(400).json({ error: message });
    }
  });

  // ── POST /api/commands/stop ─────────────────────────────────────────────
  app.post("/api/commands/stop", (req: Request, res: Response) => {
    const { id } = req.body as { id?: string };
    if (!id) {
      res.status(400).json({ error: "id is required" });
      return;
    }

    const proc = runningProcesses.get(id);
    const job = registry.jobs.find((item) => item.id === id);
    if (!job) {
      res.status(404).json({ error: "Job not found" });
      return;
    }
    if (!proc) {
      res.status(409).json({ error: "Job is not running" });
      return;
    }

    const stopped = stopJob(id);

    if (stopped) {
      job.stopRequested = true;
      globalLog(
        registry,
        `[SYSTEM] stop requested ${id}`,
      );
      flushPersist(registry);
      invalidateJobsCache();
      res.json({ status: "stop_requested", id });
    } else {
      res.status(500).json({ error: "Failed to stop job" });
    }
  });

  // ── GET /api/processes/discover ─────────────────────────────────────────
  app.get("/api/processes/discover", (_req: Request, res: Response) => {
    res.json({
      runningJobs: registry.jobs.filter((j) => j.status === "running")
        .length,
      totalJobs: registry.jobs.length,
    });
  });
}

// ── Helpers ────────────────────────────────────────────────────────────────

function resolveTemplateDefaults<T>(obj: T, npcKey: string): T {
  if (typeof obj === "string") {
    return obj.replace(/\{npcKey\}/g, npcKey) as T;
  }
  if (Array.isArray(obj)) {
    return obj.map((item) =>
      resolveTemplateDefaults(item, npcKey),
    ) as T;
  }
  if (obj && typeof obj === "object") {
    const resolved: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(
      obj as Record<string, unknown>,
    )) {
      resolved[key] = resolveTemplateDefaults(value, npcKey);
    }
    return resolved as T;
  }
  return obj;
}
