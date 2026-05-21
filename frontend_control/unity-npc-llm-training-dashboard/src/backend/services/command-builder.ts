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
      build: (payload) => ["./ucore", "sanitize", parsedDatasetPath(payload, repoRoot)],
    },
    {
      id: "dataset-eval",
      label: "Evaluate Dataset Quality",
      icon: "bar-chart",
      color: "warning",
      type: "Dataset",
      requiredFields: ["spec", "options.technique"],
      build: (payload) => [
        "./ucore",
        "dataset-eval",
        parsedSpec(payload, repoRoot),
        "--technique",
        sanitizeToken(String(optionValue(payload, "technique") || "template"), "technique"),
      ],
    },
    {
      id: "validate-spec",
      label: "Validate Spec",
      icon: "check-circle",
      color: "accent",
      type: "Validation",
      requiredFields: ["spec"],
      build: (payload) => ["./ucore", "validate-spec", parsedSpec(payload, repoRoot), "--generation-ready"],
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
        const baseModel = String(opts.baseModel || opts.model || "").trim();
        if (baseModel) args.push("--model", sanitizeToken(baseModel, "model"));
        if (opts.wandb === true || opts.wandb === "true") args.push("--wandb");
        if (opts.learningRate) args.push("--lr", String(opts.learningRate));
        if (opts.batchSize) args.push("--batch-size", String(opts.batchSize));
        if (opts.epochs) args.push("--epochs", String(opts.epochs));
        if (opts.rank) args.push("--lora-r", String(opts.rank));
        if (opts.alpha) args.push("--lora-alpha", String(opts.alpha));
        if (opts.scheduler && ["cosine", "linear", "constant"].includes(String(opts.scheduler))) args.push("--lr-scheduler", String(opts.scheduler));
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
        if (boolOptionValue(payload, "skipEval")) cmd.push("--skip-eval");
        if (boolOptionValue(payload, "skipSmoke")) cmd.push("--skip-smoke");
        const numEvalQuestions = String(optionValue(payload, "numEvalQuestions") || "5").trim();
        if (numEvalQuestions && numEvalQuestions !== "5") cmd.push("--num-eval-questions", numEvalQuestions);
        if (boolOptionValue(payload, "ollama")) cmd.push("--ollama");
        const docsManifest = String(optionValue(payload, "manifest") || "").trim();
        if (docsManifest) cmd.push("--docs-manifest", sanitizeToken(docsManifest, "manifest"));
        return cmd;
      },
    },
    {
      id: "export",
      label: "Export GGUF",
      icon: "external-link",
      color: "success",
      type: "Export",
      requiredFields: ["npcKey", "options.modelId"],
      build: ({ npcKey, options }) => [
        "./ucore",
        "export",
        sanitizeToken(requireString(npcKey, "npcKey"), "npcKey"),
        "--model",
        sanitizeToken(requireString(String(options?.modelId || ""), "modelId"), "modelId"),
      ],
    },
    {
      id: "export-adapter",
      label: "Export Adapter",
      icon: "external-link",
      color: "default",
      type: "Export",
      requiredFields: ["npcKey"],
      build: ({ npcKey }) => [
        "./ucore",
        "export-adapter",
        `outputs/${sanitizeToken(requireString(npcKey, "npcKey"), "npcKey")}`,
      ],
    },
    {
      id: "evaluate",
      label: "Evaluate Candidate",
      icon: "bar-chart",
      color: "accent",
      type: "Evaluation",
      requiredFields: ["options.baseline", "options.candidate", "spec"],
      build: (payload) => {
        const command = [
          "./ucore",
          "evaluate",
          "--baseline", parsedBaseline(payload, repoRoot),
          "--candidate", parsedCandidate(payload, repoRoot),
          "--spec", parsedSpec(payload, repoRoot),
        ];
        if (optionValue(payload, "valData").trim()) command.push("--val-data", parsedValData(payload, repoRoot));
        if (boolOptionValue(payload, "reportHtml")) command.push("--report-html");
        if (boolOptionValue(payload, "track")) command.push("--track");
        if (boolOptionValue(payload, "judge")) {
          command.push("--judge");
          const judgeModel = optionValue(payload, "judgeModel").trim();
          if (judgeModel) command.push("--judge-model", sanitizeToken(judgeModel, "judgeModel"));
        }
        const baseModel = optionValue(payload, "baseModel").trim();
        if (baseModel) command.push("--base-model", parsedBaseModel(payload, repoRoot));
        const loraWeight = optionValue(payload, "loraWeight").trim();
        if (loraWeight) command.push("--lora-weight", loraWeight);
        const numQuestions = optionValue(payload, "numQuestions").trim();
        if (numQuestions) command.push("--num-questions", numQuestions);
        const feedbackJson = optionValue(payload, "feedbackJson").trim();
        if (feedbackJson) command.push("--feedback-json", resolvePathWithinRoots(feedbackJson, "feedbackJson", [repoRoot], repoRoot));
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
      build: (payload) => ["./ucore", "smoke", parsedModelPath(payload, repoRoot), "--spec", parsedSpec(payload, repoRoot)],
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
        return args;
      },
    },
    {
      id: "feedback",
      label: "Run Feedback Loop",
      icon: "refresh-cw",
      color: "accent",
      type: "Feedback",
      requiredFields: ["feedback_json"],
      build: (payload) => {
        const feedbackJson = resolvePathWithinRoots(
          sanitizeToken(String(requireString(payload.feedback_json, "feedback_json")), "feedback_json"),
          "feedback_json",
          [repoRoot],
          repoRoot,
        );
        const args = ["./ucore", "feedback", feedbackJson];
        if (boolOptionValue(payload, "dry-run")) args.push("--dry-run");
        if (boolOptionValue(payload, "skip-gap-detection")) args.push("--skip-gap-detection");
        if (boolOptionValue(payload, "auto-retrain")) args.push("--auto-retrain");
        const trainPreset = String(payload.options?.["train-preset"] || payload["train-preset"] || "").trim();
        if (trainPreset) args.push("--train-preset", sanitizeToken(trainPreset, "train-preset"));
        const baseline = String(payload.options?.baseline || payload.baseline || "").trim();
        if (baseline) args.push("--baseline", sanitizeToken(baseline, "baseline"));
        const saveGaps = String(payload.options?.saveGaps || payload["save-gaps"] || "").trim();
        if (saveGaps) args.push("--save-gaps", sanitizeToken(saveGaps, "save-gaps"));
        if (boolOptionValue(payload, "json")) args.push("--json");
        if (boolOptionValue(payload, "skip-dataset-eval")) args.push("--skip-dataset-eval");
        const deepevalJudgeModel = String(payload.options?.deepevalJudgeModel || payload["deepeval-judge-model"] || "").trim();
        if (deepevalJudgeModel) args.push("--deepeval-judge-model", sanitizeToken(deepevalJudgeModel, "deepeval-judge-model"));
        const deepevalOllamaUrl = String(payload.options?.deepevalOllamaUrl || payload["deepeval-ollama-url"] || "").trim();
        if (deepevalOllamaUrl) args.push("--deepeval-ollama-url", sanitizeToken(deepevalOllamaUrl, "deepeval-ollama-url"));
        const deepevalCasesPerCategory = String(payload.options?.deepevalCasesPerCategory || payload["deepeval-cases-per-category"] || "").trim();
        if (deepevalCasesPerCategory) args.push("--deepeval-cases-per-category", sanitizeToken(deepevalCasesPerCategory, "deepeval-cases-per-category"));
        if (boolOptionValue(payload, "deepeval-soft-fail")) args.push("--deepeval-soft-fail");
        const regenerationTechnique = String(payload.options?.regenerationTechnique || payload["regeneration-technique"] || "").trim();
        if (regenerationTechnique) args.push("--regeneration-technique", sanitizeToken(regenerationTechnique, "regeneration-technique"));
        const regenerationModel = String(payload.options?.regenerationModel || payload["regeneration-model"] || "").trim();
        if (regenerationModel) args.push("--regeneration-model", sanitizeToken(regenerationModel, "regeneration-model"));
        const regenerationUrl = String(payload.options?.regenerationUrl || payload["regeneration-url"] || "").trim();
        if (regenerationUrl) args.push("--regeneration-url", sanitizeToken(regenerationUrl, "regeneration-url"));
        const regenerationBatchSize = String(payload.options?.regenerationBatchSize || payload["regeneration-batch-size"] || "").trim();
        if (regenerationBatchSize) args.push("--regeneration-batch-size", sanitizeToken(regenerationBatchSize, "regeneration-batch-size"));
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
        const args = ["./ucore", "quick-eval", sanitizeToken(requireString(String(options?.adapterPath || ""), "adapterPath"), "adapterPath")];
        const samples = String(options?.samples || "").trim();
        if (samples) args.push("--samples", samples);
        const specPath = String(options?.spec || "").trim();
        if (specPath) args.push("--spec", sanitizeToken(specPath, "spec"));
        const valData = String(options?.valData || "").trim();
        if (valData) args.push("--val-data", sanitizeToken(valData, "valData"));
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
        return args;
      },
    },
  ];
}

export { resolveTemplateDefaults, optionValue, boolOptionValue, DEFAULT_BASE_MODEL };
export { sanitizeToken } from "../lib/path-utils";
