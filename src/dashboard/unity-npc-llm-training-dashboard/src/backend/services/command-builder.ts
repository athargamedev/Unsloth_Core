import path from "path";
import fs from "fs";
import type { StartCommandPayload, CommandDefinition } from "../types";
import { sanitizeToken, resolvePathWithinRoots, resolvePayloadPath } from "../lib/path-utils";

// ── Default base model ─────────────────────────────────────────────────────

const DEFAULT_BASE_MODEL = process.env.DEFAULT_BASE_MODEL || "unsloth/Llama-3.2-3B-Instruct-bnb-4bit";

// ── Helper Functions ───────────────────────────────────────────────────────

const requireString = (value: unknown, fieldName: string): string => {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${fieldName} is required.`);
  }
  return value.trim();
};

const optionValue = (payload: StartCommandPayload, key: string): string => {
  const raw = (payload as Record<string, unknown>)[key] ?? payload.options?.[key];
  if (typeof raw === "string") return raw;
  if (typeof raw === "number" || typeof raw === "boolean") return String(raw);
  return "";
};

const boolOptionValue = (payload: StartCommandPayload, key: string): boolean => {
  const raw = (payload as Record<string, unknown>)[key] ?? payload.options?.[key];
  if (typeof raw === "boolean") return raw;
  if (typeof raw === "number") return raw !== 0;
  if (typeof raw === "string") return ["1", "true", "yes", "on"].includes(raw.trim().toLowerCase());
  return false;
};

const parsedSpec = (payload: StartCommandPayload, repoRoot: string): string => {
  const spec = requireString(payload.spec, "spec");
  return resolvePathWithinRoots(spec, "spec", [path.join(repoRoot, "subjects")], repoRoot);
};

const parsedDatasetPath = (payload: StartCommandPayload, repoRoot: string): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "datasetPath"), "datasetPath"),
    "datasetPath",
    [path.join(repoRoot, "subjects")],
    repoRoot,
  );
};

const parsedModelPath = (payload: StartCommandPayload, repoRoot: string): string => {
  return resolvePathWithinRoots(
    requireString(optionValue(payload, "modelPath"), "modelPath"),
    "modelPath",
    [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs")],
    repoRoot,
  );
};

const parsedBaseline = (payload: StartCommandPayload, repoRoot: string): string => {
  return resolvePayloadPath(payload, "baseline", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot], repoRoot);
};

const parsedCandidate = (payload: StartCommandPayload, repoRoot: string): string => {
  return resolvePayloadPath(payload, "candidate", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot], repoRoot);
};

const parsedBaseModel = (payload: StartCommandPayload, repoRoot: string): string => {
  return resolvePayloadPath(payload, "baseModel", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot], repoRoot);
};

const parsedValData = (payload: StartCommandPayload, repoRoot: string): string => {
  return resolvePayloadPath(payload, "valData", [path.join(repoRoot, "subjects"), repoRoot], repoRoot);
};

const appendWorkflowHooks = (args: string[], payload: StartCommandPayload): void => {
  const workflowHooks = optionValue(payload, "workflowHooks");
  if (workflowHooks) {
    // `--workflow-hooks` is a global ucore option, so argparse only accepts it
    // before the subcommand: `./ucore --workflow-hooks path train ...`.
    args.splice(1, 0, "--workflow-hooks", sanitizeToken(workflowHooks, "workflow-hooks"));
  }
};

/**
 * Recursively resolves {npcKey} templates in a defaults object.
 */
const resolveTemplateDefaults = <T>(obj: T, npcKey: string): T => {
  if (typeof obj === "string") {
    return obj.replace(/\{npcKey\}/g, npcKey) as T;
  }
  if (Array.isArray(obj)) {
    return obj.map((item) => resolveTemplateDefaults(item, npcKey)) as T;
  }
  if (obj && typeof obj === "object") {
    const resolved: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj as Record<string, unknown>)) {
      resolved[key] = resolveTemplateDefaults(value, npcKey);
    }
    return resolved as T;
  }
  return obj;
};

// ── Command Definitions ────────────────────────────────────────────────────

export function buildCommandDefinitions(repoRoot: string): CommandDefinition[] {
  return [
    {
      id: "dataset-generate",
      label: "Generate Dataset",
      icon: "database",
      color: "accent",
      type: "Dataset",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        "options.technique": { type: "string", required: false, default: "template", enum: ["template", "docs", "ollama", "openai", "anthropic"], description: "Dataset generation technique", order: 2 },
        "options.model": { type: "string", required: false, default: "", description: "HF model ID for generation", order: 3 },
        "options.modelId": { type: "string", required: false, default: "", description: "Alias for options.model", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: (payload) => {
        const args = ["./ucore", "generate", parsedSpec(payload, repoRoot)];
        const technique = String(optionValue(payload, "technique") || "").trim();
        const model = String(optionValue(payload, "model") || optionValue(payload, "modelId") || "").trim();
        if (technique) args.push("--technique", sanitizeToken(technique, "technique"));
        if (model) args.push("--model", sanitizeToken(model, "model"));
        if (technique === "ollama") args.push("--ollama");
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "dataset-sanitize",
      label: "Sanitize Dataset",
      icon: "shield",
      color: "warning",
      type: "Dataset",
      requiredFields: ["options.datasetPath"],
      schema: {
        "options.datasetPath": { type: "path", pathType: "file", roots: ["subjects"], required: true, description: "Dataset JSONL path to sanitize", order: 1 },
        output: { type: "string", required: false, default: "", description: "Output JSONL path", order: 2 },
        minLength: { type: "number", required: false, default: 10, description: "Minimum turn/response length", order: 3 },
        maxSentences: { type: "number", required: false, default: 8, description: "Max sentences per response", order: 4 },
        verbose: { type: "boolean", required: false, default: false, description: "Verbose output", order: 5 },
        spec: { type: "string", required: false, default: "", description: "NPC spec path for validation", order: 6 },
        strictCanonical: { type: "boolean", required: false, default: false, description: "Strict canonical format check", order: 7 },
        strictMode: { type: "boolean", required: false, default: false, description: "Strict validation mode", order: 8 },
        artifactCheck: { type: "string", required: false, default: "strict", enum: ["strict", "warn", "off"], description: "AI artifact detection mode", order: 9 },
        verboseArtifacts: { type: "boolean", required: false, default: false, description: "Verbose artifact detection", order: 10 },
        qualityThresholdPass: { type: "number", required: false, default: 0.7, description: "Quality threshold for pass", order: 11 },
        qualityThresholdFlag: { type: "number", required: false, default: 0.4, description: "Quality threshold for flag", order: 12 },
        qualityReport: { type: "boolean", required: false, default: false, description: "Generate quality report", order: 13 },
        discardBelowScore: { type: "number", required: false, default: 0, description: "Discard entries below score", order: 14 },
        noFixMetadata: { type: "boolean", required: false, default: false, description: "Skip metadata fixing", order: 15 },
        requireCompleteMetadata: { type: "boolean", required: false, default: false, description: "Require complete metadata", order: 16 },
        dedup: { type: "boolean", required: false, default: true, description: "Deduplicate entries", order: 17 },
        dedupReport: { type: "boolean", required: false, default: false, description: "Show dedup report", order: 18 },
        writeManifest: { type: "boolean", required: false, default: true, description: "Write dataset manifest", order: 19 },
        manifestPath: { type: "path", pathType: "file", required: false, default: "", description: "Custom manifest path", order: 20 },
        debug: { type: "boolean", required: false, default: false, description: "Debug mode", order: 21 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 22 },
      },
      build: (payload) => {
        const args = ["./ucore", "sanitize", parsedDatasetPath(payload, repoRoot)];

        const output = optionValue(payload, "output");
        if (output) args.push("--output", sanitizeToken(output, "output"));

        const minLength = optionValue(payload, "minLength");
        if (minLength) args.push("--min-length", minLength);

        const maxSentences = optionValue(payload, "maxSentences");
        if (maxSentences) args.push("--max-sentences", maxSentences);

        if (boolOptionValue(payload, "verbose")) args.push("--verbose");

        const spec = optionValue(payload, "spec");
        if (spec) args.push("--spec", sanitizeToken(spec, "spec"));

        if (boolOptionValue(payload, "strictCanonical")) args.push("--strict-canonical");
        if (boolOptionValue(payload, "strictMode")) args.push("--strict-mode");

        const artifactCheck = optionValue(payload, "artifactCheck");
        if (artifactCheck) args.push("--artifact-check", sanitizeToken(artifactCheck, "artifactCheck"));

        if (boolOptionValue(payload, "verboseArtifacts")) args.push("--verbose-artifacts");

        const qualityThresholdPass = optionValue(payload, "qualityThresholdPass");
        if (qualityThresholdPass) args.push("--quality-threshold-pass", qualityThresholdPass);

        const qualityThresholdFlag = optionValue(payload, "qualityThresholdFlag");
        if (qualityThresholdFlag) args.push("--quality-threshold-flag", qualityThresholdFlag);

        if (boolOptionValue(payload, "qualityReport")) args.push("--quality-report");

        const discardBelowScore = optionValue(payload, "discardBelowScore");
        if (discardBelowScore) args.push("--discard-below-score", discardBelowScore);

        if (boolOptionValue(payload, "noFixMetadata")) args.push("--no-fix-metadata");
        if (boolOptionValue(payload, "requireCompleteMetadata")) args.push("--require-complete-metadata");

        const dedup = optionValue(payload, "dedup");
        if (dedup === "false") args.push("--no-dedup");
        else if (dedup === "true") args.push("--dedup");

        if (boolOptionValue(payload, "dedupReport")) args.push("--dedup-report");

        const writeManifest = optionValue(payload, "writeManifest");
        if (writeManifest === "false") args.push("--no-write-manifest");
        else if (writeManifest === "true") args.push("--write-manifest");

        const manifestPath = optionValue(payload, "manifestPath");
        if (manifestPath) args.push("--manifest-path", sanitizeToken(manifestPath, "manifestPath"));

        if (boolOptionValue(payload, "debug")) args.push("--debug");

        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "dataset-eval",
      label: "Evaluate Dataset Quality",
      icon: "bar-chart",
      color: "warning",
      type: "Dataset",
      requiredFields: ["spec", "options.technique"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        "options.technique": { type: "string", required: false, default: "template", enum: ["template", "docs", "ollama", "openai", "anthropic"], description: "Dataset generation technique", order: 2 },
        "options.judgeProvider": { type: "string", required: false, default: "ollama", enum: ["ollama", "wandb"], description: "Judge provider", order: 3 },
        "options.judgeModel": { type: "string", required: false, default: "qwen2.5:7b", description: "Judge model name", order: 4 },
        "options.judgePreset": { type: "string", required: false, default: "", enum: ["judge-qwen25", "judge-llama31-exp", "judge-qwen35-exp", "judge-qwen3-exp"], description: "Judge preset", order: 5 },
        "options.ollamaBaseUrl": { type: "string", required: false, default: "http://localhost:11434", description: "Ollama server URL", order: 6 },
        "options.judgeTemperature": { type: "number", required: false, default: 0, description: "Judge temperature", order: 7 },
        "options.mode": { type: "string", required: false, default: "fast", enum: ["fast", "release"], description: "Evaluation mode (fast or release)", order: 8 },
        "options.casesPerCategory": { type: "number", required: false, default: 1, description: "Cases per category", order: 9 },
        "options.categories": { type: "string", required: false, default: "", description: "Comma-separated categories to test", order: 10 },
        "options.identifier": { type: "string", required: false, default: "", description: "Eval identifier for tracking", order: 11 },
        "options.display": { type: "string", required: false, default: "all", enum: ["all", "failing", "passing"], description: "Display filter", order: 12 },
        "options.ignoreErrors": { type: "boolean", required: false, default: false, description: "Ignore errors during eval", order: 13 },
        "options.softFail": { type: "boolean", required: false, default: false, description: "Soft fail mode", order: 14 },
        "options.output": { type: "string", required: false, default: "", description: "Output report path", order: 15 },
        "options.wandb": { type: "boolean", required: false, default: false, description: "Enable W&B logging", order: 16 },
        "options.wandbProject": { type: "string", required: false, default: "", description: "W&B project name", order: 17 },
        "options.wandbEntity": { type: "string", required: false, default: "", description: "W&B entity name", order: 18 },
        "options.wandbInferenceProject": { type: "string", required: false, default: "", description: "W&B inference project", order: 19 },
        "options.wandbInferenceEntity": { type: "string", required: false, default: "", description: "W&B inference entity", order: 20 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 21 },
      },
      build: (payload) => {
        const args = [
          "./ucore",
          "dataset-eval",
          parsedSpec(payload, repoRoot),
        ];

        const technique = String(optionValue(payload, "technique") || "template").trim();
        if (technique) args.push("--technique", sanitizeToken(technique, "technique"));

        const judgeProvider = optionValue(payload, "judgeProvider").trim();
        if (judgeProvider && judgeProvider !== "ollama") args.push("--judge-provider", sanitizeToken(judgeProvider, "judgeProvider"));

        const judgeModel = optionValue(payload, "judgeModel");
        if (judgeModel) args.push("--judge-model", sanitizeToken(judgeModel, "judgeModel"));

        const judgePreset = optionValue(payload, "judgePreset");
        if (judgePreset) args.push("--judge-preset", sanitizeToken(judgePreset, "judgePreset"));

        const ollamaBaseUrl = optionValue(payload, "ollamaBaseUrl");
        if (ollamaBaseUrl && ollamaBaseUrl !== "http://localhost:11434") args.push("--ollama-base-url", sanitizeToken(ollamaBaseUrl, "ollamaBaseUrl"));

        const judgeTemperature = optionValue(payload, "judgeTemperature");
        if (judgeTemperature && judgeTemperature !== "0") args.push("--judge-temperature", judgeTemperature);

        const mode = optionValue(payload, "mode") || optionValue(payload, "datasetEvalMode");
        if (mode && mode !== "fast") args.push("--mode", sanitizeToken(mode, "mode"));

        const casesPerCategory = optionValue(payload, "casesPerCategory");
        if (casesPerCategory && casesPerCategory !== "1") args.push("--cases-per-category", casesPerCategory);

        const categories = optionValue(payload, "categories");
        if (categories) args.push("--categories", sanitizeToken(categories, "categories"));

        const identifier = optionValue(payload, "identifier");
        if (identifier) args.push("--identifier", sanitizeToken(identifier, "identifier"));

        const display = optionValue(payload, "display");
        if (display && display !== "all") args.push("--display", sanitizeToken(display, "display"));

        if (boolOptionValue(payload, "ignoreErrors")) args.push("--ignore-errors");
        if (boolOptionValue(payload, "softFail")) args.push("--soft-fail");

        const output = optionValue(payload, "output");
        if (output) args.push("--output", sanitizeToken(output, "output"));

        if (boolOptionValue(payload, "wandb")) args.push("--wandb");
        const wandbProject = optionValue(payload, "wandbProject").trim();
        if (wandbProject) args.push("--wandb-project", sanitizeToken(wandbProject, "wandbProject"));
        const wandbEntity = optionValue(payload, "wandbEntity").trim();
        if (wandbEntity) args.push("--wandb-entity", sanitizeToken(wandbEntity, "wandbEntity"));
        const wandbInferenceProject = optionValue(payload, "wandbInferenceProject").trim();
        if (wandbInferenceProject) args.push("--wandb-inference-project", sanitizeToken(wandbInferenceProject, "wandbInferenceProject"));
        const wandbInferenceEntity = optionValue(payload, "wandbInferenceEntity").trim();
        if (wandbInferenceEntity) args.push("--wandb-inference-entity", sanitizeToken(wandbInferenceEntity, "wandbInferenceEntity"));

        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "validate-spec",
      label: "Validate Spec",
      icon: "check-circle",
      color: "accent",
      type: "Validation",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 2 },
      },
      build: (payload) => {
        const args = ["./ucore", "validate-spec", parsedSpec(payload, repoRoot), "--generation-ready"];
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "validate-config",
      label: "Validate Config",
      icon: "check-circle",
      color: "accent",
      type: "Validation",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        preset: { type: "string", required: false, default: "", description: "Training preset to validate against", order: 2 },
        "options.dataPath": { type: "string", required: false, default: "", description: "Data path override", order: 3 },
        requireCanonical: { type: "boolean", required: false, default: false, description: "Require canonical format", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: (payload) => {
        const args = ["./ucore", "validate-config", parsedSpec(payload, repoRoot)];
        const preset = String(payload.preset || "").trim();
        if (preset) args.push("--preset", sanitizeToken(preset, "preset"));
        const dataPath = String(payload.options?.dataPath || "").trim();
        if (dataPath) args.push("--data", resolvePathWithinRoots(dataPath, "dataPath", [repoRoot], repoRoot));
        if (boolOptionValue(payload, "requireCanonical")) {
          args.push("--require-canonical");
        }
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "train",
      label: "Train LoRA",
      icon: "zap",
      color: "accent",
      type: "Training",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path (--from-spec mode)", order: 1 },
        preset: { type: "string", required: false, default: "fast-3b", description: "Training preset", order: 2 },
        "options.technique": { type: "string", required: false, default: "template", enum: ["template", "docs", "ollama", "openai", "anthropic"], description: "Dataset technique", order: 3 },
        "options.modelId": { type: "string", required: false, default: "unsloth/Llama-3.2-3B-Instruct-bnb-4bit", description: "HF model ID (e.g., unsloth/Qwen3-1.7B-bnb-4bit)", order: 4 },
        "options.wandb": { type: "boolean", required: false, default: false, flagType: "BooleanOptionalAction", description: "Enable W&B logging", order: 5 },
        "options.learningRate": { type: "number", required: false, default: 0.0002, description: "Learning rate", order: 6 },
        "options.batchSize": { type: "number", required: false, default: 1, description: "Batch size", order: 7 },
        "options.epochs": { type: "number", required: false, default: 3, description: "Number of epochs", order: 8 },
        "options.rank": { type: "number", required: false, default: 16, description: "LoRA rank", order: 9 },
        "options.alpha": { type: "number", required: false, default: 32, description: "LoRA alpha", order: 10 },
        "options.scheduler": { type: "string", required: false, default: "cosine", enum: ["cosine", "linear", "constant"], description: "LR scheduler type", order: 11 },
        "options.exportGguf": { type: "boolean", required: false, default: false, flagType: "store_true", description: "Export adapter GGUF after training", order: 12 },
        "options.fullMergeExport": { type: "boolean", required: false, default: false, flagType: "store_true", description: "Full merge GGUF export (standalone)", order: 13 },
        "options.datasetEvalSkip": { type: "boolean", required: false, default: false, description: "Allow training without a fresh passing dataset quality gate (--allow-ungated-dataset)", order: 14 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 15 },
      },
      build: (payload) => {
        const args = [
          "./ucore",
          "train",
          resolvePathWithinRoots(requireString(payload.spec, "spec"), "spec", [path.join(repoRoot, "subjects")], repoRoot),
          "--from-spec",
        ];
        const preset = String(payload.preset || "").trim();
        if (preset) args.push("--preset", sanitizeToken(preset, "preset"));
        const opts = payload.options || {};
        if (opts.technique) args.push("--technique", String(opts.technique));

        // --model: HF model ID (e.g., unsloth/Qwen3-1.7B-bnb-4bit)
        // --base-model: GGUF path (for eval/LoRA loading, not for training override)
        // For training: frontend uses modelId/HF ID -> passed as --model
        const hfModel = String(opts.modelId || opts.model || "").trim();
        if (hfModel) args.push("--model", sanitizeToken(hfModel, "model"));

        // W&B: BooleanOptionalAction --wandb / --no-wandb
        const wandbOpt = opts.wandb;
        if (wandbOpt === true || wandbOpt === "true" || wandbOpt === "1") args.push("--wandb");
        if (wandbOpt === false || wandbOpt === "false" || wandbOpt === "0") args.push("--no-wandb");

        // Training hyperparameters
        if (opts.learningRate) args.push("--lr", String(opts.learningRate));
        if (opts.batchSize) args.push("--batch-size", String(opts.batchSize));
        if (opts.epochs) args.push("--epochs", String(opts.epochs));
        if (opts.rank) args.push("--lora-r", String(opts.rank));
        if (opts.alpha) args.push("--lora-alpha", String(opts.alpha));
        if (opts.scheduler && ["cosine", "linear", "constant"].includes(String(opts.scheduler))) args.push("--lr-scheduler", String(opts.scheduler));

        // Export flags
        if (boolOptionValue(payload, "exportGguf")) args.push("--export-gguf");
        if (boolOptionValue(payload, "fullMergeExport")) args.push("--full-merge-export");

        // Dataset quality is gated by a prior `ucore dataset-eval` artifact.
        // Training only supports bypassing that gate explicitly.
        if (boolOptionValue(payload, "datasetEvalSkip") || boolOptionValue(payload, "skipDatasetEval")) args.push("--allow-ungated-dataset");

        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "pipeline",
      label: "Run Full Pipeline",
      icon: "layers",
      color: "success",
      type: "Pipeline",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        preset: { type: "string", required: false, default: "fast-3b", description: "Training preset", order: 2 },
        technique: { type: "string", required: false, default: "template", enum: ["template", "docs", "ollama", "openai", "anthropic"], description: "Dataset generation technique", order: 3 },
        track: { type: "boolean", required: false, default: false, description: "Enable tracking", order: 4 },
        wandb: { type: "boolean", required: false, default: false, description: "Enable W&B logging", order: 5 },
        model: { type: "string", required: false, default: "", description: "HF model ID override", order: 6 },
        fullMergeExport: { type: "boolean", required: false, default: false, flagType: "store_true", description: "Full merge GGUF export", order: 7 },
        skipSpecValidate: { type: "boolean", required: false, default: false, description: "Skip spec validation", order: 8 },
        skipDatasetEval: { type: "boolean", required: false, default: false, description: "Skip dataset evaluation", order: 9 },
        datasetEvalMode: { type: "string", required: false, default: "fast", description: "Dataset eval mode", order: 10 },
        datasetEvalCasesPerCategory: { type: "number", required: false, default: 1, description: "Dataset eval cases per category", order: 11 },
        datasetEvalJudgeProvider: { type: "string", required: false, default: "ollama", description: "Dataset eval judge provider", order: 12 },
        datasetEvalJudgePreset: { type: "string", required: false, default: "", description: "Dataset eval judge preset", order: 13 },
        datasetEvalJudgeModel: { type: "string", required: false, default: "", description: "Dataset eval judge model", order: 14 },
        datasetEvalOllamaUrl: { type: "string", required: false, default: "http://localhost:11434", description: "Dataset eval Ollama URL", order: 15 },
        evalJudge: { type: "boolean", required: false, default: false, description: "Enable eval judge", order: 16 },
        evalJudgeProvider: { type: "string", required: false, default: "ollama", description: "Eval judge provider", order: 17 },
        evalJudgeModel: { type: "string", required: false, default: "llama3.1:latest", description: "Eval judge model", order: 18 },
        wandbInferenceProject: { type: "string", required: false, default: "", description: "W&B inference project", order: 19 },
        wandbInferenceEntity: { type: "string", required: false, default: "", description: "W&B inference entity", order: 20 },
        skipEval: { type: "boolean", required: false, default: false, description: "Skip evaluation step", order: 21 },
        skipSmoke: { type: "boolean", required: false, default: false, description: "Skip smoke test", order: 22 },
        numEvalQuestions: { type: "number", required: false, default: 5, description: "Number of evaluation questions", order: 23 },
        ollama: { type: "boolean", required: false, default: false, description: "Use Ollama for generation", order: 24 },
        manifest: { type: "string", required: false, default: "", description: "Docs manifest path", order: 25 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 26 },
      },
      build: (payload) => {
        const cmd = ["./ucore", "pipeline", parsedSpec(payload, repoRoot)];
        const preset = String(payload.preset || "").trim();
        const technique = String(optionValue(payload, "technique") || "").trim();
        const track = String(optionValue(payload, "track") || "").trim().toLowerCase();
        const wandb = String(optionValue(payload, "wandb") || "").trim().toLowerCase();
        if (preset) cmd.push("--preset", sanitizeToken(preset, "preset"));
        if (technique) cmd.push("--technique", sanitizeToken(technique, "technique"));
        if (track === "true" || track === "1") cmd.push("--track");
        if (wandb === "true" || wandb === "1") cmd.push("--wandb");
        const modelFromOpts = String(optionValue(payload, "model") || "").trim();
        if (modelFromOpts) cmd.push("--model", sanitizeToken(modelFromOpts, "model"));
        if (boolOptionValue(payload, "fullMergeExport")) cmd.push("--full-merge-export");
        if (boolOptionValue(payload, "skipSpecValidate")) cmd.push("--skip-spec-validate");
        if (boolOptionValue(payload, "skipDatasetEval")) cmd.push("--skip-dataset-eval");
        const datasetEvalMode = String(optionValue(payload, "datasetEvalMode") || "").trim();
        if (datasetEvalMode && datasetEvalMode !== "fast") cmd.push("--dataset-eval-mode", sanitizeToken(datasetEvalMode, "datasetEvalMode"));
        const datasetEvalCasesPerCategory = String(optionValue(payload, "datasetEvalCasesPerCategory") || "").trim();
        if (datasetEvalCasesPerCategory) cmd.push("--dataset-eval-cases-per-category", datasetEvalCasesPerCategory);
        const datasetEvalJudgeProvider = optionValue(payload, "datasetEvalJudgeProvider").trim();
        if (datasetEvalJudgeProvider && datasetEvalJudgeProvider !== "ollama") cmd.push("--dataset-eval-judge-provider", sanitizeToken(datasetEvalJudgeProvider, "datasetEvalJudgeProvider"));
        const datasetEvalJudgePreset = optionValue(payload, "datasetEvalJudgePreset").trim();
        if (datasetEvalJudgePreset) cmd.push("--dataset-eval-judge-preset", sanitizeToken(datasetEvalJudgePreset, "datasetEvalJudgePreset"));
        const datasetEvalJudgeModel = optionValue(payload, "datasetEvalJudgeModel").trim();
        if (datasetEvalJudgeModel) cmd.push("--dataset-eval-judge-model", sanitizeToken(datasetEvalJudgeModel, "datasetEvalJudgeModel"));
        const datasetEvalOllamaUrl = optionValue(payload, "datasetEvalOllamaUrl").trim();
        if (datasetEvalOllamaUrl && datasetEvalOllamaUrl !== "http://localhost:11434") cmd.push("--dataset-eval-ollama-url", sanitizeToken(datasetEvalOllamaUrl, "datasetEvalOllamaUrl"));
        if (boolOptionValue(payload, "evalJudge")) cmd.push("--eval-judge");
        const evalJudgeProvider = optionValue(payload, "evalJudgeProvider").trim();
        if (evalJudgeProvider && evalJudgeProvider !== "ollama") cmd.push("--eval-judge-provider", sanitizeToken(evalJudgeProvider, "evalJudgeProvider"));
        const evalJudgeModel = optionValue(payload, "evalJudgeModel").trim();
        if (evalJudgeModel && evalJudgeModel !== "llama3.1:latest") cmd.push("--eval-judge-model", sanitizeToken(evalJudgeModel, "evalJudgeModel"));
        const wandbInferenceProject = optionValue(payload, "wandbInferenceProject").trim();
        if (wandbInferenceProject) cmd.push("--wandb-inference-project", sanitizeToken(wandbInferenceProject, "wandbInferenceProject"));
        const wandbInferenceEntity = optionValue(payload, "wandbInferenceEntity").trim();
        if (wandbInferenceEntity) cmd.push("--wandb-inference-entity", sanitizeToken(wandbInferenceEntity, "wandbInferenceEntity"));
        if (boolOptionValue(payload, "skipEval")) cmd.push("--skip-eval");
        if (boolOptionValue(payload, "skipSmoke")) cmd.push("--skip-smoke");
        const numEvalQuestions = String(optionValue(payload, "numEvalQuestions") || "5").trim();
        if (numEvalQuestions && numEvalQuestions !== "5") cmd.push("--num-eval-questions", numEvalQuestions);
        if (boolOptionValue(payload, "ollama")) cmd.push("--ollama");
        const docsManifest = String(optionValue(payload, "manifest") || "").trim();
        if (docsManifest) cmd.push("--docs-manifest", sanitizeToken(docsManifest, "manifest"));
        appendWorkflowHooks(cmd, payload);
        return cmd;
      },
    },
    {
      id: "export",
      label: "Export GGUF",
      icon: "external-link",
      color: "success",
      type: "Export",
      requiredFields: ["npcKey"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key for output path resolution", order: 1 },
        "options.modelId": { type: "string", required: false, default: "", description: "HF model ID for export", order: 2 },
        "options.quantization": { type: "string", required: false, default: "f16", enum: ["f32", "f16", "bf16", "q8_0"], description: "Export quantization format", order: 3 },
        "options.fullMerge": { type: "boolean", required: false, default: false, description: "Full merge export (standalone GGUF)", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: ({ npcKey, options }) => {
        const args = [
          "./ucore",
          "export",
          sanitizeToken(requireString(npcKey, "npcKey"), "npcKey"),
        ];
        const modelId = String(options?.modelId || "").trim();
        if (modelId) args.push("--model", sanitizeToken(modelId, "modelId"));
        if (String(options?.quantization || "").trim()) args.push("--quantization", sanitizeToken(String(options?.quantization), "quantization"));
        if (boolOptionValue({ npcKey, options } as unknown as StartCommandPayload, "fullMerge")) args.push("--full-merge");
        const payload = { npcKey, options } as unknown as StartCommandPayload;
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "export-adapter",
      label: "Export Adapter",
      icon: "external-link",
      color: "default",
      type: "Export",
      requiredFields: ["npcKey"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 2 },
      },
      build: ({ npcKey }) => {
        const args = [
          "./ucore",
          "export-adapter",
          `outputs/${sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")}`,
        ];
        const payload = { npcKey } as unknown as StartCommandPayload;
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "evaluate",
      label: "Evaluate Candidate",
      icon: "bar-chart",
      color: "accent",
      type: "Evaluation",
      // Single-model mode uses "options.model" instead of baseline/candidate
      requiredFields: [],
      schema: {
        "options.model": { type: "path", pathType: "file", roots: ["exports", "outputs"], required: false, default: "", description: "Single model GGUF path (alternative to baseline/candidate)", order: 1 },
        "options.baseline": { type: "path", pathType: "file", roots: ["exports", "outputs"], required: false, default: "", description: "Baseline GGUF model path", order: 2 },
        "options.candidate": { type: "path", pathType: "file", roots: ["exports", "outputs"], required: false, default: "", description: "Candidate GGUF model path", order: 3 },
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: false, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 4 },
        "options.valData": { type: "path", pathType: "file", required: false, default: "", description: "Validation JSONL path", order: 5 },
        "options.output": { type: "string", required: false, default: "", description: "Output report path", order: 6 },
        "options.reportHtml": { type: "boolean", required: false, default: false, description: "Generate HTML report", order: 7 },
        "options.track": { type: "boolean", required: false, default: false, description: "Track results", order: 8 },
        "options.wandb": { type: "boolean", required: false, default: false, flagType: "BooleanOptionalAction", description: "Enable W&B logging", order: 9 },
        "options.wandbProject": { type: "string", required: false, default: "", description: "W&B project name", order: 10 },
        "options.wandbEntity": { type: "string", required: false, default: "", description: "W&B entity name", order: 11 },
        "options.interactive": { type: "boolean", required: false, default: false, description: "Interactive mode", order: 12 },
        "options.judge": { type: "boolean", required: false, default: false, description: "Enable LLM judge evaluation", order: 13 },
        "options.judgeProvider": { type: "string", required: false, default: "ollama", description: "Judge provider", order: 14 },
        "options.judgeModel": { type: "string", required: false, default: "", description: "Judge model name", order: 15 },
        "options.wandbInferenceProject": { type: "string", required: false, default: "", description: "W&B inference project", order: 16 },
        "options.wandbInferenceEntity": { type: "string", required: false, default: "", description: "W&B inference entity", order: 17 },
        "options.host": { type: "string", required: false, default: "", description: "llama-server host", order: 18 },
        "options.port": { type: "number", required: false, default: 8080, description: "llama-server port", order: 19 },
        "options.gpuLayers": { type: "number", required: false, default: 0, description: "GPU layers for llama-server", order: 20 },
        "options.maxTokens": { type: "number", required: false, default: 512, description: "Max tokens per response", order: 21 },
        "options.baseModel": { type: "path", pathType: "file", roots: ["exports", "outputs"], required: false, default: "", description: "Base model GGUF path for LoRA adapter loading", order: 22 },
        "options.loraWeight": { type: "number", required: false, default: 1.0, description: "LoRA adapter weight", order: 23 },
        "options.numQuestions": { type: "number", required: false, default: 5, description: "Number of evaluation questions", order: 24 },
        "options.npcKey": { type: "string", required: false, default: "", description: "NPC key override", order: 25 },
        "options.trainingMetrics": { type: "string", required: false, default: "", nargs: "?", description: "Path to training metrics JSON or flag-only", order: 26 },
        "options.feedbackJson": { type: "path", pathType: "file", required: false, default: "", description: "Feedback JSON path", order: 27 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 28 },
      },
      build: (payload) => {
        const opts = payload.options || {};
        const singleModel = String(opts.model || "").trim();
        const baseline = String(opts.baseline || "").trim();
        const candidate = String(opts.candidate || "").trim();

        // --model (single model mode) is alternative to --baseline / --candidate
        const command: string[] = ["./ucore", "evaluate"];

        if (singleModel && !baseline && !candidate) {
          // Single model mode
          command.push("--model", resolvePathWithinRoots(singleModel, "model", [path.join(repoRoot, "exports"), path.join(repoRoot, "outputs"), repoRoot], repoRoot));
        } else {
          // Compare mode: baseline + candidate (existing behavior)
          if (baseline) command.push("--baseline", parsedBaseline(payload, repoRoot));
          if (candidate) command.push("--candidate", parsedCandidate(payload, repoRoot));
        }

        const spec = String(payload.spec || "").trim();
        if (spec) command.push("--spec", parsedSpec(payload, repoRoot));

        if (optionValue(payload, "valData").trim()) command.push("--val-data", parsedValData(payload, repoRoot));

        const output = optionValue(payload, "output").trim();
        if (output) command.push("--output", resolvePathWithinRoots(output, "output", [repoRoot], repoRoot));

        if (boolOptionValue(payload, "reportHtml")) command.push("--report-html");
        if (boolOptionValue(payload, "track")) command.push("--track");

        // W&B: BooleanOptionalAction --wandb / --no-wandb
        const wandbOpt = opts.wandb;
        if (wandbOpt === true || wandbOpt === "true" || wandbOpt === "1") command.push("--wandb");
        // evaluate.py currently has --wandb but no --no-wandb; omit false values.

        const wandbProject = String(opts.wandbProject || "").trim();
        if (wandbProject) command.push("--wandb-project", sanitizeToken(wandbProject, "wandbProject"));
        const wandbEntity = String(opts.wandbEntity || "").trim();
        if (wandbEntity) command.push("--wandb-entity", sanitizeToken(wandbEntity, "wandbEntity"));

        if (boolOptionValue(payload, "interactive")) command.push("--interactive");

        if (boolOptionValue(payload, "judge")) {
          command.push("--judge");
          const judgeProvider = optionValue(payload, "judgeProvider").trim();
          if (judgeProvider && judgeProvider !== "ollama") command.push("--judge-provider", sanitizeToken(judgeProvider, "judgeProvider"));
          const judgeModel = optionValue(payload, "judgeModel").trim();
          if (judgeModel) command.push("--judge-model", sanitizeToken(judgeModel, "judgeModel"));
          const wandbInferenceProject = optionValue(payload, "wandbInferenceProject").trim();
          if (wandbInferenceProject) command.push("--wandb-inference-project", sanitizeToken(wandbInferenceProject, "wandbInferenceProject"));
          const wandbInferenceEntity = optionValue(payload, "wandbInferenceEntity").trim();
          if (wandbInferenceEntity) command.push("--wandb-inference-entity", sanitizeToken(wandbInferenceEntity, "wandbInferenceEntity"));
        }

        // llama-server connection options
        const host = String(opts.host || "").trim();
        if (host) command.push("--host", sanitizeToken(host, "host"));
        const port = String(opts.port || "").trim();
        if (port) command.push("--port", port);
        const gpuLayers = String(opts.gpuLayers || "").trim();
        if (gpuLayers) command.push("--gpu-layers", gpuLayers);
        const maxTokens = String(opts.maxTokens || "").trim();
        if (maxTokens) command.push("--max-tokens", maxTokens);

        // LoRA adapter options
        const baseModel = optionValue(payload, "baseModel").trim();
        if (baseModel) command.push("--base-model", parsedBaseModel(payload, repoRoot));
        const loraWeight = optionValue(payload, "loraWeight").trim();
        if (loraWeight) command.push("--lora-weight", loraWeight);

        const numQuestions = optionValue(payload, "numQuestions").trim();
        if (numQuestions) command.push("--num-questions", numQuestions);

        const npcKey = String(opts.npcKey || payload.npcKey || "").trim();
        if (npcKey) command.push("--npc-key", sanitizeToken(npcKey, "npcKey"));

        // --training-metrics: nargs="?", so it can be:
        // - Not present → not passed
        // - Present with no value → --training-metrics (const="")
        // - Present with value → --training-metrics <value>
        // Check raw value first: can be boolean true, or string "true", or a path
        const rawTrainingMetrics = (payload as Record<string, unknown>).trainingMetrics ?? payload.options?.trainingMetrics;
        if (rawTrainingMetrics === true || rawTrainingMetrics === "true") {
          command.push("--training-metrics");
        } else if (typeof rawTrainingMetrics === "string" && rawTrainingMetrics.trim() && rawTrainingMetrics.trim() !== "false") {
          command.push("--training-metrics", resolvePathWithinRoots(rawTrainingMetrics.trim(), "trainingMetrics", [repoRoot], repoRoot));
        }

        const feedbackJson = optionValue(payload, "feedbackJson").trim();
        if (feedbackJson) command.push("--feedback-json", resolvePathWithinRoots(feedbackJson, "feedbackJson", [repoRoot], repoRoot));

        appendWorkflowHooks(command, payload);
        return command;
      },
    },
    {
      id: "smoke",
      label: "Smoke Test",
      icon: "activity",
      color: "warning",
      type: "Validation",
      requiredFields: ["options.modelPath", "spec"],
      schema: {
        "options.modelPath": { type: "path", pathType: "file", roots: ["exports", "outputs"], required: true, description: "Model GGUF path to smoke test", order: 1 },
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 2 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 3 },
      },
      build: (payload) => {
        const args = ["./ucore", "smoke", parsedModelPath(payload, repoRoot), "--spec", parsedSpec(payload, repoRoot)];
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "deploy",
      label: "Deploy Package",
      icon: "external-link",
      color: "success",
      type: "Deploy",
      requiredFields: [],
      schema: {
        "options.unityProject": { type: "path", pathType: "dir", required: false, default: "", description: "Unity project root path", order: 1 },
        "options.dryRun": { type: "boolean", required: false, default: false, description: "Dry run (no actual deploy)", order: 2 },
        "options.skipExport": { type: "boolean", required: false, default: false, description: "Skip export step", order: 3 },
        "options.exportOnly": { type: "boolean", required: false, default: false, description: "Export only, skip deploy", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: ({ options }) => {
        const args = ["./ucore", "deploy"];
        const unityProject = String(options?.unityProject || "").trim();
        if (unityProject) args.push("--unity-project", resolvePathWithinRoots(unityProject, "unityProject", [repoRoot], repoRoot));
        if (boolOptionValue({ options } as unknown as StartCommandPayload, "dryRun")) args.push("--dry-run");
        if (boolOptionValue({ options } as unknown as StartCommandPayload, "skipExport")) args.push("--skip-export");
        if (boolOptionValue({ options } as unknown as StartCommandPayload, "exportOnly")) args.push("--export-only");
        appendWorkflowHooks(args, { options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "supabase-check",
      label: "Supabase Health Check",
      icon: "shield",
      color: "default",
      type: "System",
      requiredFields: ["npcKey"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key to check", order: 1 },
        "options.playerId": { type: "string", required: false, default: "", description: "Player ID for session check", order: 2 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 3 },
      },
      build: ({ npcKey, options }) => {
        const args = ["./ucore", "supabase-check", "--npc-key", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
        const playerId = String(options?.playerId || "").trim();
        if (playerId) args.push("--player-id", sanitizeToken(playerId, "playerId"));
        appendWorkflowHooks(args, { npcKey, options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "init",
      label: "Initialize NPC",
      icon: "database",
      color: "accent",
      type: "System",
      requiredFields: ["npcKey"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key to initialize", order: 1 },
        "options.subject": { type: "string", required: false, default: "", description: "Training subject description", order: 2 },
        "options.name": { type: "string", required: false, default: "", description: "Display name for the NPC", order: 3 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 4 },
      },
      build: ({ npcKey, options }) => {
        const args = ["./ucore", "init", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
        const subject = String(options?.subject || "").trim();
        const name = String(options?.name || "").trim();
        if (subject) args.push("--subject", subject);
        if (name) args.push("--name", name);
        appendWorkflowHooks(args, { npcKey, options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "plan-batch",
      label: "Generate Colab Notebooks",
      icon: "book-open",
      color: "success",
      type: "Pipeline",
      requiredFields: [],
      schema: {
        "options.specGlob": { type: "string", required: false, default: "subjects/NPC_specs/*.json", description: "Glob pattern for NPC specs", order: 1 },
        "options.presets": { type: "string", required: false, default: "fast-3b,premium-3b,premium-8b,safe-any", description: "Comma-separated preset list", order: 2 },
        "options.localVram": { type: "number", required: false, default: 4.0, description: "Local VRAM in GB", order: 3 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 4 },
      },
      build: (payload) => {
        const args = ["./ucore", "plan-batch", "--generate-colab-notebooks"];
        const specGlob = String(payload.options?.specGlob || "subjects/NPC_specs/*.json").trim();
        if (specGlob) args.push("--spec-glob", specGlob);
        const presets = String(payload.options?.presets || "fast-3b,premium-3b,premium-8b,safe-any").trim();
        if (presets) args.push("--presets", presets);
        const localVram = String(payload.options?.localVram || "4.0").trim();
        if (localVram) args.push("--local-vram-gb", localVram);
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "docs-manifest-generate",
      label: "Generate Docs Manifest Dataset",
      icon: "file-text",
      color: "accent",
      type: "Dataset",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        manifest: { type: "string", required: false, default: "", description: "Docs manifest path", order: 2 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 3 },
      },
      build: (payload) => {
        const args = ["./ucore", "generate", parsedSpec(payload, repoRoot), "--technique", "docs"];
        const manifest = String(optionValue(payload, "manifest") || "").trim();
        if (manifest) args.push("--docs-manifest", sanitizeToken(manifest, "manifest"));
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "feedback",
      label: "Run Feedback Loop",
      icon: "refresh-cw",
      color: "accent",
      type: "Feedback",
      requiredFields: ["options.feedbackJson"],
      schema: {
        "options.feedbackJson": { type: "path", pathType: "file", required: true, description: "Feedback JSON path", order: 1 },
        winRateThreshold: { type: "number", required: false, default: 0.5, description: "Win rate threshold", order: 2 },
        qualityThreshold: { type: "number", required: false, default: 0.6, description: "Quality threshold", order: 3 },
        violationThreshold: { type: "number", required: false, default: 0.3, description: "Violation threshold", order: 4 },
        "dry-run": { type: "boolean", required: false, default: false, flagType: "store_true", description: "Dry run mode", order: 5 },
        auto: { type: "boolean", required: false, default: false, flagType: "store_true", description: "Auto mode", order: 6 },
        "skip-gap-detection": { type: "boolean", required: false, default: false, flagType: "store_true", description: "Skip gap detection", order: 7 },
        "auto-retrain": { type: "boolean", required: false, default: false, flagType: "store_true", description: "Auto retrain", order: 8 },
        trainPreset: { type: "string", required: false, default: "fast-3b", description: "Training preset for retrain", order: 9 },
        baseline: { type: "string", required: false, default: "", description: "Baseline identifier", order: 10 },
        "save-gaps": { type: "path", pathType: "file", required: false, default: "", description: "Path to save gap analysis", order: 11 },
        json: { type: "boolean", required: false, default: false, flagType: "store_true", description: "JSON output", order: 12 },
        "strategy-profile": { type: "string", required: false, default: "npc-production-grounded", description: "Strategy profile for anti-loop decisions", order: 13 },
        "deepeval-judge-provider": { type: "string", required: false, default: "ollama", description: "DeepEval judge provider", order: 14 },
        "deepeval-judge-model": { type: "string", required: false, default: "", description: "DeepEval judge model", order: 15 },
        "deepeval-judge-preset": { type: "string", required: false, default: "", description: "DeepEval judge preset", order: 16 },
        "deepeval-ollama-url": { type: "string", required: false, default: "http://localhost:11434", description: "DeepEval Ollama URL", order: 17 },
        "deepeval-cases-per-category": { type: "number", required: false, default: 1, description: "DeepEval cases per category", order: 18 },
        "deepeval-soft-fail": { type: "boolean", required: false, default: false, flagType: "store_true", description: "DeepEval soft fail", order: 19 },
        wandb: { type: "boolean", required: false, default: false, flagType: "store_true", description: "Enable W&B logging", order: 20 },
        "wandb-project": { type: "string", required: false, default: "", description: "W&B project name", order: 21 },
        "wandb-entity": { type: "string", required: false, default: "", description: "W&B entity name", order: 22 },
        "wandb-inference-project": { type: "string", required: false, default: "", description: "W&B inference project", order: 23 },
        "wandb-inference-entity": { type: "string", required: false, default: "", description: "W&B inference entity", order: 24 },
        "regeneration-technique": { type: "string", required: false, default: "", description: "Regeneration dataset technique", order: 25 },
        regenerationPreset: { type: "string", required: false, default: "", description: "Regeneration training preset", order: 26 },
        "regeneration-model": { type: "string", required: false, default: "", description: "Regeneration model name", order: 27 },
        "regeneration-url": { type: "string", required: false, default: "", description: "Regeneration Ollama URL", order: 28 },
        "regeneration-batch-size": { type: "number", required: false, default: 4, description: "Regeneration batch size", order: 29 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 30 },
      },
      build: (payload) => {
        const opts = payload.options || {};

        const feedbackJson = String(payload.feedback_json || opts.feedbackJson || "").trim();
        if (!feedbackJson) {
          throw new Error("options.feedbackJson is required for feedback.");
        }

        const args: string[] = ["./ucore", "feedback", resolvePathWithinRoots(
          sanitizeToken(feedbackJson, "feedback_json"),
          "feedback_json",
          [repoRoot],
          repoRoot,
        )];

        // Thresholds
        const winRateThreshold = String(opts.winRateThreshold || "").trim();
        if (winRateThreshold) args.push("--win-rate-threshold", winRateThreshold);
        const qualityThreshold = String(opts.qualityThreshold || "").trim();
        if (qualityThreshold) args.push("--quality-threshold", qualityThreshold);
        const violationThreshold = String(opts.violationThreshold || "").trim();
        if (violationThreshold) args.push("--violation-threshold", violationThreshold);

        if (boolOptionValue(payload, "dry-run") || boolOptionValue(payload, "dryRun")) args.push("--dry-run");
        if (boolOptionValue(payload, "auto")) args.push("--auto");
        if (boolOptionValue(payload, "skip-gap-detection") || boolOptionValue(payload, "skipGapDetection")) args.push("--skip-gap-detection");
        if (boolOptionValue(payload, "auto-retrain") || boolOptionValue(payload, "autoRetrain")) args.push("--auto-retrain");

        const trainPreset = String(payload.options?.trainPreset || payload.options?.["train-preset"] || payload["train-preset"] || "").trim();
        if (trainPreset) args.push("--train-preset", sanitizeToken(trainPreset, "train-preset"));
        const baseline = String(payload.options?.baseline || payload.baseline || "").trim();
        if (baseline) args.push("--baseline", sanitizeToken(baseline, "baseline"));
        const saveGaps = String(payload.options?.saveGaps || payload["save-gaps"] || "").trim();
        if (saveGaps) args.push("--save-gaps", resolvePathWithinRoots(saveGaps, "save-gaps", [repoRoot], repoRoot));
        if (boolOptionValue(payload, "json")) args.push("--json");

        // DeepEval judge
        const deepevalJudgeProvider = String(payload.options?.deepevalJudgeProvider || payload["deepeval-judge-provider"] || "").trim();
        if (deepevalJudgeProvider && deepevalJudgeProvider !== "ollama") args.push("--deepeval-judge-provider", sanitizeToken(deepevalJudgeProvider, "deepeval-judge-provider"));
        const deepevalJudgeModel = String(payload.options?.deepevalJudgeModel || payload["deepeval-judge-model"] || "").trim();
        if (deepevalJudgeModel) args.push("--deepeval-judge-model", sanitizeToken(deepevalJudgeModel, "deepeval-judge-model"));
        const deepevalJudgePreset = String(payload.options?.deepevalJudgePreset || payload["deepeval-judge-preset"] || "").trim();
        if (deepevalJudgePreset) args.push("--deepeval-judge-preset", sanitizeToken(deepevalJudgePreset, "deepeval-judge-preset"));
        const deepevalOllamaUrl = String(payload.options?.deepevalOllamaUrl || payload["deepeval-ollama-url"] || "").trim();
        if (deepevalOllamaUrl) args.push("--deepeval-ollama-url", sanitizeToken(deepevalOllamaUrl, "deepeval-ollama-url"));
        const deepevalCasesPerCategory = String(payload.options?.deepevalCasesPerCategory || payload["deepeval-cases-per-category"] || "").trim();
        if (deepevalCasesPerCategory) args.push("--deepeval-cases-per-category", deepevalCasesPerCategory);
        if (boolOptionValue(payload, "deepeval-soft-fail") || boolOptionValue(payload, "deepevalSoftFail")) args.push("--deepeval-soft-fail");
        const wandb = String(payload.options?.wandb || payload.wandb || "").trim().toLowerCase();
        if (wandb === "true" || wandb === "1") args.push("--wandb");
        const wandbProject = String(payload.options?.wandbProject || payload["wandb-project"] || "").trim();
        if (wandbProject) args.push("--wandb-project", sanitizeToken(wandbProject, "wandb-project"));
        const wandbEntity = String(payload.options?.wandbEntity || payload["wandb-entity"] || "").trim();
        if (wandbEntity) args.push("--wandb-entity", sanitizeToken(wandbEntity, "wandb-entity"));
        const wandbInferenceProject = String(payload.options?.wandbInferenceProject || payload["wandb-inference-project"] || "").trim();
        if (wandbInferenceProject) args.push("--wandb-inference-project", sanitizeToken(wandbInferenceProject, "wandb-inference-project"));
        const wandbInferenceEntity = String(payload.options?.wandbInferenceEntity || payload["wandb-inference-entity"] || "").trim();
        if (wandbInferenceEntity) args.push("--wandb-inference-entity", sanitizeToken(wandbInferenceEntity, "wandb-inference-entity"));

        // Regeneration options
        const regenerationTechnique = String(payload.options?.regenerationTechnique || payload["regeneration-technique"] || "").trim();
        if (regenerationTechnique) args.push("--regeneration-technique", sanitizeToken(regenerationTechnique, "regeneration-technique"));
        const regenerationPreset = String(payload.options?.regenerationPreset || "").trim();
        if (regenerationPreset) args.push("--regeneration-preset", sanitizeToken(regenerationPreset, "regeneration-preset"));
        const regenerationModel = String(payload.options?.regenerationModel || payload["regeneration-model"] || "").trim();
        if (regenerationModel) args.push("--regeneration-model", sanitizeToken(regenerationModel, "regeneration-model"));
        const regenerationUrl = String(payload.options?.regenerationUrl || payload["regeneration-url"] || "").trim();
        if (regenerationUrl) args.push("--regeneration-url", sanitizeToken(regenerationUrl, "regeneration-url"));
        const regenerationBatchSize = String(payload.options?.regenerationBatchSize || payload["regeneration-batch-size"] || "").trim();
        if (regenerationBatchSize) args.push("--regeneration-batch-size", regenerationBatchSize);

        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "generate-ollama",
      label: "Generate Dataset (Ollama Optimized)",
      icon: "database",
      color: "accent",
      type: "Dataset",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        model: { type: "string", required: false, default: "llama3.1-3060-chat:latest", description: "Ollama model name", order: 2 },
        batchSize: { type: "number", required: false, default: 4, description: "Concurrent generation tasks", order: 3 },
        temperature: { type: "number", required: false, default: 0.6, description: "Generation temperature", order: 4 },
        multiTurnRatio: { type: "number", required: false, default: 0.25, description: "Fraction of two-turn dialogues", order: 5 },
        seed: { type: "number", required: false, default: 42, description: "Random seed", order: 6 },
        url: { type: "string", required: false, default: "http://localhost:11434", description: "Ollama server URL", order: 7 },
        maxRetries: { type: "number", required: false, default: 3, description: "Max retries per generation", order: 8 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 9 },
      },
      build: (payload) => {
        const args = ["./ucore", "generate-ollama", parsedSpec(payload, repoRoot)];
        const model = String(optionValue(payload, "model") || "").trim();
        if (model) args.push("--model", sanitizeToken(model, "model"));
        const batchSize = Number(optionValue(payload, "batchSize"));
        if (batchSize && batchSize !== 4) args.push("--batch-size", String(batchSize));
        const temperature = Number(optionValue(payload, "temperature"));
        if (temperature && temperature !== 0.6) args.push("--temperature", String(temperature));
        const mtRatio = Number(optionValue(payload, "multiTurnRatio"));
        if (mtRatio && mtRatio !== 0.25) args.push("--multi-turn-ratio", String(mtRatio));
        const seed = Number(optionValue(payload, "seed"));
        if (seed && seed !== 42) args.push("--seed", String(seed));
        const url = String(optionValue(payload, "url") || "").trim();
        if (url && url !== "http://localhost:11434") args.push("--url", sanitizeToken(url, "url"));
        const maxRetries = Number(optionValue(payload, "maxRetries"));
        if (maxRetries && maxRetries !== 3) args.push("--max-retries", String(maxRetries));
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "target-plan",
      label: "Plan Target DAG",
      icon: "git-branch",
      color: "accent",
      type: "Pipeline",
      requiredFields: ["npcKey"],
      cli: { source: "ucore", command: "target", subcommand: "plan" },
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.technique": { type: "string", required: false, default: "", enum: ["", "template", "docs", "ollama", "openai", "anthropic"], description: "Dataset technique/artifact lane", order: 2 },
        "options.targetStage": { type: "string", required: false, default: "evaluate", enum: ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate"], description: "Target stage", order: 3 },
        "options.artifactIndex": { type: "path", pathType: "file", required: false, default: "", description: "ArtifactRegistry JSONL path override", order: 4 },
        "options.profile": { type: "string", required: false, default: "npc-production-grounded", description: "NPC profile label", order: 5 },
        "options.json": { type: "boolean", required: false, default: true, description: "Output JSON", order: 6 },
      },
      build: ({ npcKey, options }) => {
        const args = ["./ucore", "target", "plan", "--npc-key", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
        const technique = String(options?.technique || "").trim();
        if (technique) args.push("--technique", sanitizeToken(technique, "technique"));
        const targetStage = String(options?.targetStage || "evaluate").trim();
        if (targetStage) args.push("--target-stage", sanitizeToken(targetStage, "targetStage"));
        const artifactIndex = String(options?.artifactIndex || "").trim();
        if (artifactIndex) args.push("--artifact-index", resolvePathWithinRoots(artifactIndex, "artifactIndex", [repoRoot], repoRoot));
        const profile = String(options?.profile || "npc-production-grounded").trim();
        if (profile) args.push("--profile", sanitizeToken(profile, "profile"));
        if (options?.json !== false && options?.json !== "false") args.push("--json");
        return args;
      },
    },
    {
      id: "target-run",
      label: "Run Target DAG",
      icon: "play-circle",
      color: "success",
      type: "Pipeline",
      requiredFields: ["npcKey"],
      cli: { source: "ucore", command: "target", subcommand: "run" },
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.technique": { type: "string", required: false, default: "", enum: ["", "template", "docs", "ollama", "openai", "anthropic"], description: "Dataset technique/artifact lane", order: 2 },
        "options.targetStage": { type: "string", required: false, default: "evaluate", enum: ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate"], description: "Target stage", order: 3 },
        "options.profile": { type: "string", required: false, default: "npc-production-grounded", description: "NPC profile label", order: 4 },
        "options.dryRun": { type: "boolean", required: false, default: true, description: "Preview commands without executing", order: 5 },
        "options.resume": { type: "boolean", required: false, default: false, description: "Skip already-completed stages", order: 6 },
        "options.forceStage": { type: "string", required: false, default: "", enum: ["", "generate", "sanitize", "dataset_eval", "train", "export", "evaluate"], description: "Force re-run a specific stage", order: 7 },
        "options.artifactIndex": { type: "path", pathType: "file", required: false, default: "", description: "ArtifactRegistry JSONL path override", order: 8 },
        "options.json": { type: "boolean", required: false, default: true, description: "Output JSON", order: 9 },
      },
      build: ({ npcKey, options }) => {
        const args = ["./ucore", "target", "run", "--npc-key", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
        const technique = String(options?.technique || "").trim();
        if (technique) args.push("--technique", sanitizeToken(technique, "technique"));
        const targetStage = String(options?.targetStage || "evaluate").trim();
        if (targetStage) args.push("--target-stage", sanitizeToken(targetStage, "targetStage"));
        const profile = String(options?.profile || "npc-production-grounded").trim();
        if (profile) args.push("--profile", sanitizeToken(profile, "profile"));
        if (options?.dryRun !== false && options?.dryRun !== "false") args.push("--dry-run");
        if (options?.resume === true || options?.resume === "true") args.push("--resume");
        const forceStage = String(options?.forceStage || "").trim();
        if (forceStage) args.push("--force-stage", sanitizeToken(forceStage, "forceStage"));
        const artifactIndex = String(options?.artifactIndex || "").trim();
        if (artifactIndex) args.push("--artifact-index", resolvePathWithinRoots(artifactIndex, "artifactIndex", [repoRoot], repoRoot));
        if (options?.json !== false && options?.json !== "false") args.push("--json");
        return args;
      },
    },
    {
      id: "compare-canonical-runs",
      label: "Compare Canonical Runs",
      icon: "bar-chart-2",
      color: "accent",
      type: "Evaluation",
      requiredFields: ["options.baselineRunId", "options.candidateRunId"],
      cli: { source: "ucore", command: "compare-canonical-runs" },
      schema: {
        "options.baselineRunId": { type: "string", required: true, description: "Baseline canonical run id", order: 1 },
        "options.candidateRunId": { type: "string", required: true, description: "Candidate canonical run id", order: 2 },
        "options.output": { type: "path", pathType: "file", required: false, default: "", description: "Comparison report path", order: 3 },
        "options.registryPath": { type: "path", pathType: "file", required: false, default: "", description: "ExperimentRegistry JSONL path override", order: 4 },
        "options.refreshIndex": { type: "boolean", required: false, default: false, description: "Refresh .pipeline/runs_index.jsonl before compare", order: 5 },
        "options.json": { type: "boolean", required: false, default: true, description: "Output JSON", order: 6 },
      },
      build: ({ options }) => {
        const baselineRunId = sanitizeToken(requireString(String(options?.baselineRunId || ""), "baselineRunId"), "baselineRunId");
        const candidateRunId = sanitizeToken(requireString(String(options?.candidateRunId || ""), "candidateRunId"), "candidateRunId");
        const args = ["./ucore", "compare-canonical-runs", baselineRunId, candidateRunId];
        const output = String(options?.output || "").trim();
        if (output) args.push("--output", resolvePathWithinRoots(output, "output", [repoRoot], repoRoot));
        const registryPath = String(options?.registryPath || "").trim();
        if (registryPath) args.push("--registry-path", resolvePathWithinRoots(registryPath, "registryPath", [repoRoot], repoRoot));
        if (options?.refreshIndex === true || options?.refreshIndex === "true") args.push("--refresh-index");
        if (options?.json !== false && options?.json !== "false") args.push("--json");
        return args;
      },
    },
    {
      id: "promote",
      label: "Promote Candidate",
      icon: "award",
      color: "success",
      type: "Deployment",
      requiredFields: ["npcKey", "options.candidateRunId"],
      cli: { source: "ucore", command: "promote" },
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.candidateRunId": { type: "string", required: true, description: "Candidate run id that won comparison", order: 2 },
        "options.registryPath": { type: "path", pathType: "file", required: false, default: "", description: "ExperimentRegistry JSONL path override", order: 3 },
        "options.dryRun": { type: "boolean", required: false, default: true, description: "Preview only; no deployment pointer changes", order: 4 },
        "options.json": { type: "boolean", required: false, default: true, description: "Output JSON", order: 5 },
      },
      build: ({ npcKey, options }) => {
        const args = [
          "./ucore",
          "promote",
          "--npc-key",
          sanitizeToken(requireString(npcKey, "npcKey"), "npcKey"),
          "--candidate-run-id",
          sanitizeToken(requireString(String(options?.candidateRunId || ""), "candidateRunId"), "candidateRunId"),
        ];
        const registryPath = String(options?.registryPath || "").trim();
        if (registryPath) args.push("--registry-path", resolvePathWithinRoots(registryPath, "registryPath", [repoRoot], repoRoot));
        if (options?.dryRun !== false && options?.dryRun !== "false") args.push("--dry-run");
        if (options?.json !== false && options?.json !== "false") args.push("--json");
        return args;
      },
    },
    {
      id: "compare-runs",
      label: "Compare Training Runs",
      icon: "bar-chart",
      color: "accent",
      type: "Evaluation",
      requiredFields: ["npcKey", "options.baselineRun", "options.candidateRun"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.baselineRun": { type: "string", required: true, description: "Baseline training run ID", order: 2 },
        "options.candidateRun": { type: "string", required: true, description: "Candidate training run ID", order: 3 },
        "options.spec": { type: "string", required: false, default: "", description: "Spec path override", order: 4 },
        "options.numQuestions": { type: "number", required: false, default: 5, description: "Number of evaluation questions", order: 5 },
        "options.judge": { type: "boolean", required: false, default: false, description: "Enable LLM judge evaluation", order: 6 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 7 },
      },
      build: ({ npcKey, options }) => {
        const args = [
          "./ucore",
          "compare-runs",
          sanitizeToken(requireString(npcKey, "npcKey"), "npcKey"),
          "--baseline-run",
          sanitizeToken(requireString(String(options?.baselineRun || ""), "baselineRun"), "baselineRun"),
          "--candidate-run",
          sanitizeToken(requireString(String(options?.candidateRun || ""), "candidateRun"), "candidateRun"),
        ];
        const specPath = String(options?.spec || "").trim();
        if (specPath) args.push("--spec", sanitizeToken(specPath, "spec"));
        const numQuestions = String(options?.numQuestions || "").trim();
        if (numQuestions) args.push("--num-questions", numQuestions);
        const judge = options?.judge;
        if (judge === true || judge === "true" || judge === "1") args.push("--judge");
        appendWorkflowHooks(args, { npcKey, options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "export-resume",
      label: "Export Resume",
      icon: "external-link",
      color: "success",
      type: "Export",
      requiredFields: ["npcKey"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.modelId": { type: "string", required: false, default: "", description: "HF model ID", order: 2 },
        "options.quantization": { type: "string", required: false, default: "f16", enum: ["f32", "f16", "bf16", "q8_0"], description: "Export quantization format", order: 3 },
        "options.skipF16": { type: "boolean", required: false, default: false, description: "Skip F16 conversion", order: 4 },
        "options.timeoutSeconds": { type: "number", required: false, default: 3600, description: "Export timeout in seconds", order: 5 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 6 },
      },
      build: ({ npcKey, options }) => {
        const args = ["./ucore", "export-resume", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
        const modelId = String(options?.modelId || "").trim();
        if (modelId) args.push("--model", sanitizeToken(modelId, "modelId"));
        const quantization = String(options?.quantization || "").trim();
        if (quantization) args.push("--quantization", sanitizeToken(quantization, "quantization"));
        if (boolOptionValue({ options } as unknown as StartCommandPayload, "skipF16")) args.push("--skip-f16");
        const timeoutSeconds = Number(options?.timeoutSeconds);
        if (timeoutSeconds) args.push("--timeout-seconds", String(timeoutSeconds));
        appendWorkflowHooks(args, { npcKey, options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "track",
      label: "Track Metrics",
      icon: "activity",
      color: "accent",
      type: "Evaluation",
      requiredFields: ["npcKey"],
      schema: {
        npcKey: { type: "string", required: true, description: "NPC key", order: 1 },
        "options.model": { type: "string", required: false, default: "", description: "Model identifier", order: 2 },
        "options.show": { type: "boolean", required: false, default: false, description: "Show tracking data", order: 3 },
        "options.winRate": { type: "number", required: false, default: 0, description: "Win rate to record", order: 4 },
        "options.avgQuality": { type: "number", required: false, default: 0, description: "Average quality score", order: 5 },
        "options.valLoss": { type: "number", required: false, default: 0, description: "Validation loss", order: 6 },
        "options.notes": { type: "string", required: false, default: "", description: "Tracking notes", order: 7 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 8 },
      },
      build: ({ npcKey, options }) => {
        const args = ["./ucore", "track", "--npc-key", sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")];
        const model = String(options?.model || "").trim();
        if (model) args.push("--model", sanitizeToken(model, "model"));
        if (options?.show === true || options?.show === "true") args.push("--show");
        const winRate = String(options?.winRate || "").trim();
        if (winRate) args.push("--win-rate", winRate);
        const avgQuality = String(options?.avgQuality || "").trim();
        if (avgQuality) args.push("--avg-quality", avgQuality);
        const valLoss = String(options?.valLoss || "").trim();
        if (valLoss) args.push("--val-loss", valLoss);
        const notes = String(options?.notes || "").trim();
        if (notes) args.push("--notes", sanitizeToken(notes, "notes"));
        appendWorkflowHooks(args, { npcKey, options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "quick-eval",
      label: "Quick Evaluation",
      icon: "zap",
      color: "warning",
      type: "Evaluation",
      requiredFields: ["options.adapterPath"],
      schema: {
        "options.adapterPath": { type: "path", pathType: "file", required: true, description: "Adapter GGUF path", order: 1 },
        "options.samples": { type: "number", required: false, default: 5, description: "Number of samples to test", order: 2 },
        "options.spec": { type: "path", pathType: "file", required: false, default: "", description: "Spec path", order: 3 },
        "options.valData": { type: "path", pathType: "file", required: false, default: "", description: "Validation data path", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: ({ options }) => {
        const args = ["./ucore", "quick-eval", "--adapter", sanitizeToken(requireString(String(options?.adapterPath || ""), "adapterPath"), "adapterPath")];
        const samples = String(options?.samples || "").trim();
        if (samples) args.push("--samples", samples);
        const specPath = String(options?.spec || "").trim();
        if (specPath) args.push("--spec", sanitizeToken(specPath, "spec"));
        const valData = String(options?.valData || "").trim();
        if (valData) args.push("--val-data", sanitizeToken(valData, "valData"));
        appendWorkflowHooks(args, { options } as unknown as StartCommandPayload);
        return args;
      },
    },
    {
      id: "audit",
      label: "Audit System",
      icon: "shield",
      color: "default",
      type: "System",
      requiredFields: [],
      schema: {
        full: { type: "boolean", required: false, default: false, flagType: "store_true", description: "Full audit check", order: 1 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 2 },
      },
      build: (payload) => {
        const args = ["./ucore", "audit", "check"];
        if (boolOptionValue(payload, "full")) args.push("--full");
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "batch-export",
      label: "Batch Export",
      icon: "external-link",
      color: "success",
      type: "Export",
      requiredFields: [],
      schema: {
        "options.npc": { type: "string", required: false, default: "", description: "NPC key filter", order: 1 },
        "options.quantization": { type: "string", required: false, default: "f16", enum: ["f32", "f16", "bf16", "q8_0"], description: "Export quantization format", order: 2 },
        "options.model": { type: "string", required: false, default: "", description: "HF model ID", order: 3 },
        skipF16: { type: "boolean", required: false, default: false, description: "Skip F16 conversion", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: (payload) => {
        const args = ["./ucore", "batch-export"];
        const npc = String(payload?.options?.npc || "").trim();
        if (npc) args.push("--npc", sanitizeToken(npc, "npc"));
        const quantization = String(payload?.options?.quantization || "").trim();
        if (quantization) args.push("--quantization", sanitizeToken(quantization, "quantization"));
        const model = String(payload?.options?.model || "").trim();
        if (model) args.push("--model", sanitizeToken(model, "model"));
        if (boolOptionValue(payload, "skipF16")) args.push("--skip-f16");
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "plan-execution",
      label: "Plan Execution",
      icon: "book-open",
      color: "success",
      type: "Pipeline",
      requiredFields: ["spec"],
      schema: {
        spec: { type: "path", pathType: "file", roots: ["subjects"], required: true, default: "subjects/NPC_specs/{npcKey}.json", description: "Subject spec path", order: 1 },
        preset: { type: "string", required: false, default: "", description: "Training preset", order: 2 },
        localVramGb: { type: "number", required: false, default: 4.0, description: "Local VRAM in GB", order: 3 },
        json: { type: "boolean", required: false, default: false, flagType: "store_true", description: "JSON output", order: 4 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 5 },
      },
      build: (payload) => {
        const args = ["./ucore", "plan-execution", "--spec", parsedSpec(payload, repoRoot)];
        const preset = String(payload.preset || "").trim();
        if (preset) args.push("--preset", sanitizeToken(preset, "preset"));
        const localVramGb = optionValue(payload, "localVramGb");
        if (localVramGb) args.push("--local-vram-gb", localVramGb);
        if (boolOptionValue(payload, "json")) args.push("--json");
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
    {
      id: "tb-reader",
      label: "TensorBoard Reader",
      icon: "bar-chart",
      color: "accent",
      type: "Evaluation",
      requiredFields: ["options.runDir"],
      schema: {
        "options.runDir": { type: "string", required: true, description: "Training run directory", order: 1 },
        "options.indent": { type: "number", required: false, default: 2, description: "JSON indent level", order: 2 },
        "options.workflowHooks": { type: "string", required: false, default: "", description: "Workflow hooks JSONL path", order: 3 },
      },
      build: (payload) => {
        const args = ["./ucore", "tb-reader", "--run-dir", sanitizeToken(
          requireString(optionValue(payload, "runDir"), "runDir"), "runDir")];
        const indent = Number(optionValue(payload, "indent"));
        if (indent && indent !== 2) args.push("--indent", String(indent));
        appendWorkflowHooks(args, payload);
        return args;
      },
    },
  ];
}

export { resolveTemplateDefaults, optionValue, boolOptionValue, DEFAULT_BASE_MODEL };
export { sanitizeToken } from "../lib/path-utils";
