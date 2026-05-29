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
      build: (payload) => {
        const args = [
          "./ucore",
          "dataset-eval",
          parsedSpec(payload, repoRoot),
        ];

        const technique = String(optionValue(payload, "technique") || "template").trim();
        if (technique) args.push("--technique", sanitizeToken(technique, "technique"));

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
          const judgeModel = optionValue(payload, "judgeModel").trim();
          if (judgeModel) command.push("--judge-model", sanitizeToken(judgeModel, "judgeModel"));
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
        const deepevalJudgeModel = String(payload.options?.deepevalJudgeModel || payload["deepeval-judge-model"] || "").trim();
        if (deepevalJudgeModel) args.push("--deepeval-judge-model", sanitizeToken(deepevalJudgeModel, "deepeval-judge-model"));
        const deepevalJudgePreset = String(payload.options?.deepevalJudgePreset || payload["deepeval-judge-preset"] || "").trim();
        if (deepevalJudgePreset) args.push("--deepeval-judge-preset", sanitizeToken(deepevalJudgePreset, "deepeval-judge-preset"));
        const deepevalOllamaUrl = String(payload.options?.deepevalOllamaUrl || payload["deepeval-ollama-url"] || "").trim();
        if (deepevalOllamaUrl) args.push("--deepeval-ollama-url", sanitizeToken(deepevalOllamaUrl, "deepeval-ollama-url"));
        const deepevalCasesPerCategory = String(payload.options?.deepevalCasesPerCategory || payload["deepeval-cases-per-category"] || "").trim();
        if (deepevalCasesPerCategory) args.push("--deepeval-cases-per-category", deepevalCasesPerCategory);
        if (boolOptionValue(payload, "deepeval-soft-fail") || boolOptionValue(payload, "deepevalSoftFail")) args.push("--deepeval-soft-fail");

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
      id: "compare-runs",
      label: "Compare Training Runs",
      icon: "bar-chart",
      color: "accent",
      type: "Evaluation",
      requiredFields: ["npcKey", "options.baselineRun", "options.candidateRun"],
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
