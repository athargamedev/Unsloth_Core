# Frontend ↔ CLI Parity Analysis

**Date:** 2026-05-22  
**Files analyzed:**
- `ucore` (992 lines — 28 subcommands)
- `frontend_control/unity-npc-llm-training-dashboard/src/backend/services/command-builder.ts` (570 lines — 22 command definitions)
- `frontend_control/unity-npc-llm-training-dashboard/src/backend/routes/commands.ts` (384 lines — schemas)
- `frontend_control/unity-npc-llm-training-dashboard/src/App.tsx` (1952 lines)
- `frontend_control/unity-npc-llm-training-dashboard/src/components/EvalWorkflowPanel.tsx` (397 lines)
- `frontend_control/unity-npc-llm-training-dashboard/src/components/TrainingSuite.tsx` (241 lines)
- `frontend_control/unity-npc-llm-training-dashboard/src/components/DatasetPipelinePanel.tsx` (738 lines)
- `frontend_control/unity-npc-llm-training-dashboard/src/components/FeedbackLoopPanel.tsx` (321 lines)
- `frontend_control/unity-npc-llm-training-dashboard/src/components/SystemHub.tsx` (72 lines)

---

## 1. Command Coverage Summary

| # | Subcommand | CLI flags | In command-builder? | UI form exists? | Parity |
|---|-----------|-----------|--------------------|-----------------|--------|
| 1 | `generate` | 8 flags | ✅ `dataset-generate` | ✅ DatasetPipelinePanel | ⚠️ Partial |
| 2 | `generate-ollama` | 15 flags | ✅ | ✅ DatasetPipelinePanel | ⚠️ Partial |
| 3 | `sanitize` | **22 flags** | ✅ `dataset-sanitize` | ✅ DatasetPipelinePanel | ❌ CRITICAL |
| 4 | `dataset-eval` | **15 flags** | ✅ | ✅ DatasetPipelinePanel | ❌ CRITICAL |
| 5 | `train` | 14 flags | ✅ | ✅ TrainingSuite | ⚠️ Partial |
| 6 | `smoke` | 4 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 7 | `validate-config` | 8 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 8 | `validate-spec` | 7 flags | ✅ | ✅ DatasetPipelinePanel | ⚠️ Partial |
| 9 | `export` | 8 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 10 | `export-resume` | 5 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 11 | `export-adapter` | 4 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 12 | `deploy` | 4 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 13 | `evaluate` | **22 flags** | ✅ | ✅ EvalWorkflowPanel | ❌ MAJOR |
| 14 | `quick-eval` | 6 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 15 | `track` | 6 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 16 | `compare-runs` | 6 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 17 | `feedback` | **18 flags** | ✅ | ✅ FeedbackLoopPanel | ❌ MAJOR |
| 18 | `supabase-check` | 3 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 19 | `pipeline` | 14 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 20 | `plan-execution` | 4 flags | ❌ Not defined | ❌ No UI form | ❌ MISSING |
| 21 | `plan-batch` | 8 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 22 | `batch-export` | 4 flags | ✅ | ❌ No UI form | ❌ MISSING |
| 23 | `tb-reader` | 2 flags | ❌ Not defined | ❌ No UI form | ❌ MISSING |
| 24 | `init` | 4 flags | ✅ | ✅ SystemHub | ⚠️ Partial |
| 25 | `audit` | 1 flag | ✅ | ❌ No UI form | ❌ MISSING |
| 26 | `docs-manifest-generate` | 1 flag | ✅ | ❌ No UI form | ❌ MISSING |
| 27 | `smoke` (from pipeline) | n/a | ✅ | ❌ No UI form | ❌ MISSING |
| 28 | `config/spec validation` | n/a | ✅ | ✅ DatasetPipelinePanel | ⚠️ Partial |

---

## 2. Deep Dive by Subcommand

### 2.1 `sanitize` — CRITICAL GAPS

**CLI flags (22 total):**
`input` (positional), `--output`, `--min-length` (default=10), `--max-sentences` (default=5), `--verbose`, `--spec`, `--strict-canonical`, `--strict-mode`, `--artifact-check` (choices: strict/warn/off), `--verbose-artifacts`, `--quality-threshold-pass` (default=70), `--quality-threshold-flag` (default=50), `--quality-report`, `--discard-below-score` (default=0), `--no-fix-metadata`, `--require-complete-metadata`, `--dedup`/`--no-dedup` (default=True), `--dedup-report`, `--write-manifest`/`--no-write-manifest` (default=True), `--manifest-path`, `--debug`, `--workflow-hooks`

**Frontend (`command-builder.ts` line 121-122):**
```ts
build: (payload) => ["./ucore", "sanitize", parsedDatasetPath(payload, repoRoot)],
```

**GAPS:**
- ❌ Passes ONLY the input path — ZERO flags forwarded
- Missing: ALL 21 remaining sanitization flags
- No UI controls in DatasetPipelinePanel for any sanitize option
- **Impact**: Frontend can never produce clean datasets with customized thresholds

### 2.2 `dataset-eval` — MAJOR GAPS

**CLI flags (15 total):**
`spec` (positional), `--technique` (default=template), `--judge-model`, `--judge-preset` (4 choices), `--ollama-base-url` (default=http://localhost:11434), `--judge-temperature` (default=0.0), `--cases-per-category` (default=5), `--categories`, `--identifier`, `--display` (all/failing/passing), `--ignore-errors`, `--soft-fail`, `--output`, `--workflow-hooks`

**Frontend (`command-builder.ts` lines 125-137):**
```ts
build: (payload) => [
  "./ucore", "dataset-eval", parsedSpec(payload, repoRoot),
  "--technique", sanitizeToken(String(optionValue(payload, "technique") || "template"), "technique"),
],
```

**GAPS:**
- ❌ Missing: `--judge-model`, `--judge-preset`, `--ollama-base-url`, `--cases-per-category` (default=5), `--categories`, `--soft-fail`, `--display`, `--identifier`, `--ignore-errors`, `--judge-temperature`, `--output`
- ❌ No UI controls in DatasetPipelinePanel for DeepEval configuration
- **Impact**: Quality gate uses defaults with no user control

### 2.3 `evaluate` — MAJOR GAPS

**CLI flags (22 total):**
`--baseline`, `--candidate`, `--model` (single model), `--spec`, `--val-data`, `--num-questions` (default=10), `--output`, `--report-html`, `--judge`, `--judge-model` (default=llama3.1:latest), `--track`, `--wandb`, `--wandb-project` (default=unsloth-core), `--wandb-entity`, `--interactive`, `--port` (default=8888), `--gpu-layers` (default=99), `--max-tokens` (default=256), `--feedback-json`, `--base-model`, `--lora-weight` (default=1.0), `--host` (default=127.0.0.1), `--training-metrics`, `--npc-key`, `--workflow-hooks`

**Frontend (`command-builder.ts` lines 263-288):**
```ts
build: (payload) => {
  const command = [
    "./ucore", "evaluate",
    "--baseline", parsedBaseline(payload, repoRoot),
    "--candidate", parsedCandidate(payload, repoRoot),
    "--spec", parsedSpec(payload, repoRoot),
  ];
  if (optionValue(payload, "valData").trim()) command.push("--val-data", ...);
  if (boolOptionValue(payload, "reportHtml")) command.push("--report-html");
  if (boolOptionValue(payload, "track")) command.push("--track");
  if (boolOptionValue(payload, "judge")) { command.push("--judge"); ... }
  if (optionValue(payload, "judgeModel")) command.push("--judge-model", ...);
  if (optionValue(payload, "baseModel")) command.push("--base-model", ...);
  if (optionValue(payload, "loraWeight")) command.push("--lora-weight", ...);
  if (optionValue(payload, "numQuestions")) command.push("--num-questions", ...);
  if (optionValue(payload, "feedbackJson")) command.push("--feedback-json", ...);
  return command;
},
```

**UI (EvalWorkflowPanel.tsx):** Has `baseline`, `candidate`, `baseModel`, `loraWeight`, `numQuestions`, `reportHtml`, `track`, `feedbackJson`, `judge`, `judgeModel`.

**GAPS:**
- ❌ Missing from command-builder AND UI: `--val-data`, `--wandb`, `--wandb-project`, `--wandb-entity`, `--host`, `--port`, `--gpu-layers`, `--max-tokens`, `--interactive`, `--model` (single model mode), `--training-metrics`, `--npc-key`, `--workflow-hooks`, `--output`
- ❌ UI has no field for: val-data, wandb config, host/port, gpu-layers, max-tokens, training-metrics, npc-key

### 2.4 `train` — MODERATE GAPS

**CLI flags:** `config_or_spec` (positional), `--from-spec`, `--preset`, `--technique`, `--model`, `--export-gguf`, `--full-merge-export`, `--wandb`/`--no-wandb`, `--lr`, `--batch-size`, `--epochs`, `--lora-r`, `--lora-alpha`, `--lr-scheduler`

**Frontend (`command-builder.ts` lines 167-195):**
```ts
build: (payload) => {
  // --from-spec always added
  // preset, technique, model, wandb, learningRate, batchSize, epochs, rank, alpha, scheduler
  // NO export-gguf, NO full-merge-export
}
```

**UI (TrainingSuite.tsx):** Has spec, preset, technique, baseModel, rank, alpha, learningRate, scheduler, batchSize, epochs, wandb checkbox.

**GAPS:**
- ❌ `--export-gguf` flag never passed from frontend (but CLI also has `--from-spec` so pipeline handles this separately)
- ❌ `--full-merge-export` missing from command-builder (though present in `pipeline`)
- ❌ No `--no-wandb` support
- ❌ No `--lr-scheduler` passing from TrainingSuite (UE dropdown exists but flag encoding not verified)
- ✅ `--lr-scheduler` is actually forwarded (line 192 in command-builder.ts)

### 2.5 `generate` — MODERATE GAPS

**CLI flags:** `spec` (positional), `--ollama`, `--technique` (choices), `--docs-manifest`, `--model`, `--concept-focus`

**Frontend (`command-builder.ts` lines 98-113):** Passes technique, model/modelId, and `--ollama` for ollama technique.

**GAPS:**
- ❌ Missing: `--concept-focus` (not in command-builder)
- ❌ Missing: `--docs-manifest` (not supported by dataset-generate command, only by `docs-manifest-generate`)

### 2.6 `generate-ollama` — MODERATE GAPS

**CLI flags:** `spec` (positional), `--model` (default=llama3.1-3060-chat:latest), `--url`, `--batch-size` (default=4), `--max-retries` (default=3), `--temperature` (default=0.6), `--multi-turn-ratio` (default=0.25), `--seed` (default=42), `--output`, `--no-validation`, `--val-split` (default=0.12), `--check-health`, `--pull-model`, `--concept-focus`, `--dry-run`

**Frontend (`command-builder.ts` lines 423-447):** Passes model, batchSize, temperature, multiTurnRatio, seed, url, maxRetries.

**UI (DatasetPipelinePanel.tsx):** Has model, batchSize, temperature, multiTurnRatio, seed.

**GAPS:**
- ❌ Missing from command-builder: `--output`, `--no-validation`, `--val-split`, `--check-health`, `--pull-model`, `--concept-focus`, `--dry-run`
- ❌ Missing from UI: Same 7 flags above
- ⚠️ Default model mismatch: CLI defaults to `llama3.1-3060-chat:latest`, UI defaults to `llama3.2:3b`

### 2.7 `feedback` — MODERATE GAPS

**CLI flags (18 total):**
`feedback_json` (positional), `--win-rate-threshold` (0.5), `--quality-threshold` (25.0), `--violation-threshold` (1), `--dry-run`, `--auto`, `--skip-gap-detection`, `--save-gaps`, `--json`, `--auto-retrain`, `--train-preset` (fast-3b), `--baseline`, `--regeneration-technique` (template/ollama), `--regeneration-preset`, `--regeneration-model`, `--regeneration-url`, `--regeneration-batch-size` (4), `--deepeval-judge-preset`, `--deepeval-judge-model`, `--deepeval-ollama-url`, `--deepeval-cases-per-category` (5), `--deepeval-soft-fail`

**Frontend (`command-builder.ts` lines 379-421):** Passes feedback_json, dry-run, skip-gap-detection, auto-retrain, train-preset, baseline, save-gaps, json, skip-dataset-eval, deepeval-judge-model, deepeval-ollama-url, deepeval-cases-per-category, deepeval-soft-fail, regeneration-technique, regeneration-model, regeneration-url, regeneration-batch-size.

**UI (FeedbackLoopPanel.tsx):** Has dryRun, skipGapDetection, autoRetrain, trainPreset.

**GAPS:**
- ❌ Missing from command-builder: `--win-rate-threshold`, `--quality-threshold`, `--violation-threshold`, `--auto`, `--regeneration-preset`, `--deepeval-judge-preset`
- ❌ Missing from UI: Many flags — no UI for thresholds, auto-accept, regeneration-preset, baseline, save-gaps, json, deepeval configs, regeneration configs
- **Impact**: Feedback loop can't be tuned from UI for threshold-based decisions

### 2.8 `pipeline` — MODERATE GAPS

**CLI flags (14):** `spec`, `--preset`, `--ollama`, `--technique`, `--docs-manifest`, `--model`, `--track`, `--wandb`, `--full-merge-export`, `--skip-smoke`, `--skip-eval`, `--skip-spec-validate`, `--skip-dataset-eval`, `--num-eval-questions`

**Frontend (`command-builder.ts` lines 197-227):** Covers most pipeline flags.

**GAPS:**
- ❌ No dedicated UI form for pipeline command (only accessible via SystemHub command cards)
- ❌ Missing: `--docs-manifest` (in pipeline builder) — covered in command-builder
- ✅ Most flags present in command-builder

### 2.9 Missing Subcommand Forms (NO UI)

These subcommands exist in `command-builder.ts` but have **no dedicated UI form**:

| Subcommand | Where it's accessible |
|-----------|---------------------|
| `smoke` | SystemHub card only |
| `validate-config` | SystemHub card only |
| `export` | Right sidebar button (hardcoded) |
| `export-adapter` | SystemHub card only |
| `export-resume` | SystemHub card only |
| `deploy` | SystemHub card only |
| `quick-eval` | SystemHub card only |
| `track` | SystemHub card only |
| `compare-runs` | SystemHub card only |
| `supabase-check` | SystemHub card only |
| `batch-export` | SystemHub card only |
| `audit` | SystemHub card only |
| `docs-manifest-generate` | SystemHub card only |
| `plan-batch` | SystemHub card only |
| `plan-execution` | ❌ Not even in command-builder |
| `tb-reader` | ❌ Not even in command-builder |

All these SystemHub cards launch a generic modal with no specialized flag fields (just the `requiredFields` from schemas).

### 2.10 Plan Flow Gaps

The `plan-execution` and `tb-reader` subcommands are **completely absent** from `command-builder.ts` (not defined at all) and have no UI.

---

## 3. Schema Coverage Analysis (`baseDefaultsByCommand` in `commands.ts`)

The schema definitions at `commands.ts` lines 83-206 define what fields the UI knows about. Only **3 commands** have schema entries:

| Command | Schema fields | Coverage |
|---------|--------------|----------|
| `dataset-generate` | spec, options.technique | ⚠️ Missing: docs-manifest, model, concept-focus, ollama |
| `train` | spec, preset, options.learningRate, options.batchSize, options.epochs, options.rank, options.alpha, options.baseModel, options.technique, options.wandb | ⚠️ Missing: export-gguf, full-merge-export, no-wandb, lr-scheduler |
| `pipeline` | spec, preset, options.technique, options.track, options.wandb | ⚠️ Missing: 9 other pipeline flags |

**Every other command** gets only `requiredFields` auto-populated with type=string, no defaults, no enums, no descriptions.

---

## 4. Action Plan

### 🔴 CRITICAL (blocks core functionality)

| Priority | What | Where | Fix |
|----------|------|-------|-----|
| **C-1** | `sanitize` only passes path, no flags | `command-builder.ts:121-122` | Add ALL sanitize flags to build function + add schema to `baseDefaultsByCommand` |
| **C-2** | `dataset-eval` passes no DeepEval flags | `command-builder.ts:130-136` | Add judge-model, judge-preset, ollama-base-url, cases-per-category, soft-fail, categories, output |
| **C-3** | No UI form for sanitize options | `DatasetPipelinePanel.tsx` | Add sanitization control panel (quality thresholds, dedup, artifact-check, etc.) |
| **C-4** | No UI form for DeepEval configuration | `DatasetPipelinePanel.tsx` | Add judge model/URL/temperature/cases controls |
| **C-5** | `feedback` can't pass thresholds from UI | `FeedbackLoopPanel.tsx` | Add win-rate, quality, violation thresholds + regeneration config + deepeval config |

### 🟠 HIGH (limits usability)

| Priority | What | Where | Fix |
|----------|------|-------|-----|
| **H-1** | `evaluate` missing `--training-metrics`, `--wandb-entity`, `--host`, `--port`, `--gpu-layers`, `--max-tokens`, `--wandb-project`, `--npc-key` | `command-builder.ts:263-288`, `EvalWorkflowPanel.tsx` | Add missing evaluate flags to builder + UI |
| **H-2** | `train` missing `--export-gguf`, `--full-merge-export` from command-builder | `command-builder.ts:167-195` | Add export-gguf flag option |
| **H-3** | `generate` missing `--concept-focus` | `command-builder.ts:98-113` | Add concept-focus support |
| **H-4** | `generate-ollama` missing `--check-health`, `--pull-model`, `--dry-run`, `--no-validation`, `--val-split`, `--output` | `command-builder.ts:423-447` | Add missing flags |
| **H-5** | `plan-execution` not in command-builder | `command-builder.ts` | Add plan-execution command definition |
| **H-6** | `tb-reader` not in command-builder | `command-builder.ts` | Add tb-reader command definition |
| **H-7** | Schema only covers 3/22 commands with proper defaults/enums | `commands.ts:83-206` | Add schemas for all commands with enum choices, defaults, descriptions |

### 🟡 MEDIUM (UI/consistency improvements)

| Priority | What | Where | Fix |
|----------|------|-------|-----|
| **M-1** | No dedicated UI for `export` (hardcoded in sidebar only) | `App.tsx` right sidebar | Create ExportPanel with full flag configuration |
| **M-2** | No dedicated UI for `smoke` command | New component | Create SmokeTestPanel |
| **M-3** | No dedicated UI for `compare-runs` | New component | Create CompareRunsPanel |
| **M-4** | SystemHub generic modal shows all commands but with minimal fields | `commands.ts` schema | Add proper schemas so modal renders helpful fields |
| **M-5** | `pipeline` no dedicated form — hidden in SystemHub | New component | Create PipelinePanel with all 14 flags |
| **M-6** | Default model mismatch: CLI `generate-ollama` uses `llama3.1-3060-chat:latest`, UI uses `llama3.2:3b` | `DatasetPipelinePanel.tsx:50` | Align defaults |
| **M-7** | Missing `--workflow-hooks` from ALL frontend commands | `command-builder.ts` | Add workflow-hooks to every build function |
| **M-8** | Quick-eval `--adapter` is positional in docs but `--adapter` flag in CLI definition | `command-builder.ts:517-533` | Verify adapter path handling |

---

## 5. Specific File + Line References

### Command Builder Gaps (`src/backend/services/command-builder.ts`)

| Line(s) | Command | Issue |
|---------|---------|-------|
| 121-122 | `dataset-sanitize` | Only passes input path — 0/22 flags |
| 130-136 | `dataset-eval` | Only passes spec + technique — 0/12 extra flags |
| 173-194 | `train` | Missing `--export-gguf`, `--full-merge-export` |
| 263-288 | `evaluate` | Missing `--val-data`, `--wandb`, `--wandb-project`, `--wandb-entity`, `--host`, `--port`, `--gpu-layers`, `--max-tokens`, `--interactive`, `--training-metrics`, `--npc-key`, `--output`, `--model` |
| 379-421 | `feedback` | Missing `--win-rate-threshold`, `--quality-threshold`, `--violation-threshold`, `--auto`, `--regeneration-preset`, `--deepeval-judge-preset` |
| 98-113 | `dataset-generate` | Missing `--concept-focus`, `--docs-manifest` |
| 423-447 | `generate-ollama` | Missing `--output`, `--no-validation`, `--val-split`, `--check-health`, `--pull-model`, `--concept-focus`, `--dry-run` |
| N/A | `plan-execution` | **Not defined at all** |
| N/A | `tb-reader` | **Not defined at all** |

### Schema Gaps (`src/backend/routes/commands.ts`)

| Line(s) | Command | Issue |
|---------|---------|-------|
| 83-206 | All commands | Only 3 commands have schema entries (dataset-generate, train, pipeline) |
| 213-237 | Schema fallback | Every other command gets only `requiredFields` auto-populated |
| 87-106 | `dataset-generate` | Missing: docs-manifest, model, concept-focus, ollama |
| 107-168 | `train` | Missing: export-gguf, full-merge-export, no-wandb, lr-scheduler |
| 169-205 | `pipeline` | Missing: docs-manifest, model, full-merge-export, skip-*, num-eval-questions, ollama shortcut |

### UI Component Gaps

| File | Lines | Issue |
|------|-------|-------|
| `components/DatasetPipelinePanel.tsx` | 119-148 | `dataset-sanitize` step passes zero flags — hardcoded path only |
| `components/DatasetPipelinePanel.tsx` | 133-148 | `dataset-eval` step passes technique only |
| `components/DatasetPipelinePanel.tsx` | 49-56 | Ollama config missing: maxRetries, url, no-validation, val-split, check-health, pull-model, dry-run |
| `components/EvalWorkflowPanel.tsx` | 29-42 | Eval config missing: val-data, wandb, wandb-project, wandb-entity, host, port, gpu-layers, max-tokens, interactive, training-metrics, npc-key, output, model |
| `components/TrainingSuite.tsx` | 137-149 | No UI for export-gguf, full-merge-export |
| `components/FeedbackLoopPanel.tsx` | 13-17 | Missing: win-rate-threshold, quality-threshold, violation-threshold, auto, regeneration-*, deepeval-*, baseline, save-gaps |
| `App.tsx` | 1402+ | SystemHub list: compares, supabase-check, deploy, remote config — all use generic modal |
| `App.tsx` | 842-853 | Export sidebar button is hardcoded, no form |
