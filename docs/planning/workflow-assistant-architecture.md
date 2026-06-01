# Workflow Assistant Architecture Plan

## Goal

Build a dashboard-native AI workflow assistant for Unsloth_Core that helps Unity developers locally create structured NPC datasets, fine-tune LoRA adapters, export GGUF adapters, evaluate results, and iterate improvements for LLMUnity runtime use.

This assistant is **not** another NPC dataset/model. It is an operational copilot over project docs, source state, logs, metrics, artifacts, and safe command orchestration.

## Current State Review

### Existing UI

- `src/components/AIAssistant.tsx`
  - Chat UI exists.
  - Calls `/api/assistant`, `/api/assistant/load`, `/api/assistant/unload`, `/api/assistant/execute`.
  - These routes are currently not implemented in the backend.
  - Hardcoded wording references `llama3.1` and Onyx retrieval.
  - Can render runnable `./ucore` commands, but direct execution needs a stronger confirmation/safety path.

- `src/components/WorkflowAssistantPanel.tsx`
  - Currently focused on generating a `workflow_assistant` docs dataset.
  - This treats the assistant too much like an NPC/spec training target.
  - Uses stale paths:
    - `subjects/workflow_assistant.json`
    - `docs/corpora/${selectedManifest}`
  - Current project state has the workflow assistant manifest under:
    - `frontend_control/unity-npc-llm-training-dashboard/workflow_assistant/docs/workflow_assistant_docs.json`

### Existing Backend/Data APIs to Reuse

- Jobs and logs:
  - `/api/jobs/state`
  - `/api/jobs/:id/logs`
  - `/api/logs`
  - `/api/watch-logs`
- Dataset quality:
  - `/api/datasets/quality-summary/:npcKey/:technique`
  - `/api/datasets/quality-failures/:npcKey/:technique`
- Runs and training artifacts:
  - `/api/runs`
  - `/api/run/:npcKey/:runId`
  - `/api/tensorboard?npcKey=...&runId=...`
- Evaluation and feedback:
  - `/api/eval-reports`
  - `/api/eval-reports/file`
  - `/api/feedback-results`
  - `/api/feedback-result/file`
- Pipeline history:
  - `/api/pipeline/runs`
  - `/api/pipeline/runs/:run_id`
  - `/api/pipeline/runs/:run_id/hooks`
  - `/api/pipeline/runs/:run_id/log`
- Commands:
  - `/api/available-commands`
  - `/api/command-schemas`
  - `/api/commands/start`

## Product Definition

The Workflow Assistant should answer and act in these modes:

1. **Explain**
   - Explain pipeline stages, commands, current UI tabs, presets, datasets, exports, and LLMUnity deployment path.

2. **Inspect**
   - Read current jobs, logs, workflow hooks, quality reports, eval reports, TensorBoard metrics, exports, and feedback gap files.

3. **Compare**
   - Compare runs, datasets, eval reports, quality gates, model exports, and LoRA configs.

4. **Diagnose**
   - Identify likely causes of failed generation, sanitization, training, export, eval, Supabase, Ollama, or llama.cpp issues.

5. **Recommend**
   - Propose next commands, dataset fixes, prompt/reference-doc improvements, training preset changes, eval changes, or deployment checks.

6. **Orchestrate safely**
   - Prepare command payloads through existing `/api/commands/start` schemas.
   - Never run expensive or destructive work without explicit user confirmation.

## Non-Goals

- Do not train a `workflow_assistant` LoRA as if it were a Unity NPC.
- Do not rely on an NPC spec as the primary assistant brain.
- Do not use the same pipeline as user NPC training for the assistant.
- Do not compete for GPU/VRAM with dataset generation, DeepEval, training, export, or llama-server evaluation.

## Recommended Architecture

```text
React Chat UI
  -> /api/assistant/chat
      -> Assistant Orchestrator
          -> Resource Guard
          -> Context Collector
          -> Retrieval Layer
          -> Tool Planner
          -> Local LLM Client
          -> Response Validator
  -> /api/assistant/actions/preview
  -> /api/assistant/actions/confirm
```

### Frontend Components

Replace the current split with two distinct surfaces:

1. `WorkflowAssistantChat.tsx`
   - Conversational assistant.
   - Shows current resource status: idle / blocked by training / assistant model loaded / unloaded.
   - Supports context chips: selected NPC, run, dataset, job, report.
   - Displays evidence citations from files/API artifacts.
   - Displays proposed commands as pending actions, not auto-run snippets.

2. `WorkflowAssistantPanel.tsx`
   - Operational dashboard for assistant capabilities.
   - Sections:
     - Current project snapshot
     - Recent failures
     - Quality gate summary
     - Training/eval comparisons
     - Suggested next actions
     - Assistant model/resource status

### Backend Modules

Add:

- `src/backend/routes/assistant.ts`
- `src/backend/services/assistant-orchestrator.ts`
- `src/backend/services/assistant-context.ts`
- `src/backend/services/assistant-retrieval.ts`
- `src/backend/services/assistant-resource-guard.ts`
- `src/backend/services/assistant-actions.ts`
- `src/backend/services/assistant-prompts.ts`

## Resource and Model Policy

Machine target: RTX 3060 6GB class local workflow.

### Primary rule

The assistant must never race with GPU-heavy jobs:

- training
- dataset-eval with Ollama judge
- Ollama generation
- export/full merge
- llama-server evaluation
- batch export

### Resource guard behavior

Before every assistant LLM call:

1. Check `/api/jobs/state` or registry directly for running jobs with types:
   - `Training`
   - `Dataset` when command is `generate-ollama` or `dataset-eval`
   - `Evaluation`
   - `Export`
   - `Pipeline`
2. Check `ollama ps` and `nvidia-smi`.
3. If GPU-heavy work is active:
   - Do not load assistant model.
   - Answer from deterministic context and retrieval only when possible.
   - Otherwise return: “Assistant LLM paused while training/eval is running.”
4. If assistant model is loaded and a heavy job starts:
   - Auto-unload assistant model first.
   - Record event in logs.

### Model selection

Use a configurable profile file, e.g.:

`frontend_control/unity-npc-llm-training-dashboard/workflow_assistant/assistant_config.json`

Recommended profiles:

```json
{
  "defaultProfile": "balanced_idle",
  "profiles": {
    "fast_safe": {
      "provider": "ollama",
      "model": "qwen2.5:3b",
      "num_ctx": 8192,
      "num_parallel": 1,
      "keep_alive": "0s",
      "useWhen": "low latency or uncertain VRAM"
    },
    "balanced_idle": {
      "provider": "ollama",
      "model": "qwen3:latest",
      "num_ctx": 8192,
      "num_parallel": 1,
      "keep_alive": "0s",
      "useWhen": "no GPU-heavy jobs active"
    },
    "cpu_fallback": {
      "provider": "ollama",
      "model": "qwen2.5:3b",
      "num_ctx": 4096,
      "num_gpu": 0,
      "num_parallel": 1,
      "keep_alive": "0s",
      "useWhen": "GPU reserved for pipeline"
    }
  }
}
```

Notes:

- Use `qwen3:latest` only when the GPU is idle.
- Set assistant `num_parallel=1` even if global Ollama is tuned for DeepEval concurrency.
- Use `keep_alive: 0s` or short TTL so the model unloads after each answer.
- Expose model profile in UI, but mark heavy models as unavailable during training/eval.

## Context Sources

The assistant should retrieve compact, structured context from:

### Static project knowledge

- `AGENTS.md`
- `README.md`
- `docs/training-workflow.md`
- `docs/npc-data-rl-execution-contract.md`
- `subjects/reference_docs/README.md`
- `configs/ollama-model-presets.yaml`
- `configs/presets/*.yaml`
- `ucore --help` output snapshots

### Runtime state

- jobs registry
- command schemas
- system status
- Ollama status
- telemetry
- watch logs

### Artifacts/results

- `subjects/datasets/{npc}/{technique}/train_clean.jsonl`
- `quality_summary.json`
- `quality_failures.json`
- `outputs/{npc}/runs/**/trainer_state.json`
- TensorBoard scalar summaries
- `exports/{npc}/*.gguf`
- eval reports and feedback JSON
- `workflow_hooks.jsonl`
- Supabase status and tracked test results

## Retrieval Strategy

Do not dump large logs directly into prompts.

Use a server-side context collector that returns summaries:

```ts
interface AssistantContextBundle {
  selectedNpc?: string;
  selectedTechnique?: string;
  selectedRunId?: string;
  projectSnapshot: {...};
  activeJobs: JobSummary[];
  recentErrors: LogExcerpt[];
  datasetQuality?: QualitySummary;
  qualityFailures?: FailureSummary[];
  trainingMetrics?: TrainingMetricSummary;
  evalSummary?: EvalSummary;
  feedbackGaps?: FeedbackGapSummary[];
  commandSchemas: Record<string, unknown>;
  evidence: EvidenceRef[];
}
```

Each evidence ref should include:

- source type
- file/API path
- timestamp
- line/window if available
- compact excerpt

## Prompt Structure

### System prompt

```text
You are the Unsloth_Core Workflow Assistant, an operational copilot for local Unity NPC LoRA production.

Mission: help Unity developers create high-quality structured datasets, fine-tune LoRA adapters, export GGUF adapters, evaluate them, and deploy them through LLMUnity.

You are not an NPC character. Do not roleplay as an NPC. Do not invent project state.
Use only provided context, retrieved docs, logs, metrics, command schemas, and explicit user input.

Priorities:
1. Protect local resources. Never recommend running assistant LLM work concurrently with training, dataset-eval, Ollama generation, export, or llama-server eval.
2. Preserve quality gates. Do not weaken dataset thresholds or bypass gates unless the user explicitly requests development bypass.
3. Prefer exact `./ucore` commands and dashboard actions.
4. Always cite evidence when diagnosing logs/results.
5. When uncertain, ask for the missing artifact instead of guessing.
6. Focus on the goal: best local workflow for Unity developers generating NPC datasets and runtime LoRA adapters for LLMUnity.

Response style:
- concise
- actionable
- file paths and command flags exact
- separate Findings, Cause, Recommendation, Next Command when diagnosing
```

### Developer prompt / policy block

```text
Tool/action policy:
- You may propose commands, but execution requires explicit user confirmation.
- Never start training, export, dataset generation, dataset-eval, feedback auto-retrain, or model loading while another GPU-heavy job is active.
- If logs contain errors, quote the exact error excerpt and source.
- If comparing runs, use metrics and artifacts, not subjective guesses.
- If recommending dataset changes, preserve the five required categories: identity, teaching, dialogue, quest, refusal.
```

### Task-specific prompt templates

1. **Diagnose failed job**
   - Inputs: job logs, command, exit code, workflow hooks, related artifacts.
   - Output: root cause, evidence, fix, retry command.

2. **Compare training runs**
   - Inputs: config snapshots, TensorBoard metrics, eval reports, export sizes.
   - Output: winner, tradeoffs, next experiment.

3. **Analyze dataset quality**
   - Inputs: quality summary/failures, sanitizer report, sample rows.
   - Output: failing categories, generation fix, primer fix, regenerate command.

4. **Prepare Unity deployment**
   - Inputs: exports, base model path, NPC spec, Supabase status.
   - Output: LLMUnity loading checklist and deployment command.

5. **Plan next workflow step**
   - Inputs: current artifact graph.
   - Output: next safe command with rationale.

## Action Safety

Assistant-generated actions should be structured:

```ts
interface ProposedAction {
  id: string;
  label: string;
  risk: 'read_only' | 'light' | 'gpu_heavy' | 'destructive';
  commandId?: string;
  payload?: Record<string, unknown>;
  shellPreview?: string;
  requiresConfirmation: boolean;
  blockedReason?: string;
}
```

Rules:

- Read-only analysis can run immediately.
- `gpu_heavy` actions require:
  - no active GPU-heavy job
  - user confirmation
  - assistant model unloaded first
- Destructive actions require double confirmation.
- Use command schemas instead of raw shell wherever possible.

## UI Design Requirements

### Chat header

Show:

- assistant profile/model
- resource state: Idle / Paused / Blocked by Training / LLM Loaded
- current selected NPC/run/dataset context
- unload button

### Message rendering

Assistant answers should support:

- Evidence citations
- Proposed action cards
- Diff-like comparisons
- Metric tables
- Error excerpts
- “Open artifact” links

### Context controls

Add chips/dropdowns:

- NPC key
- dataset technique
- run ID
- job ID
- eval report
- feedback result

### Suggested prompts

- “Why did the latest job fail?”
- “Compare latest two runs for this NPC.”
- “What should I do before training?”
- “Analyze quality failures for this dataset.”
- “Is it safe to run dataset-eval now?”
- “Prepare LLMUnity deployment checklist.”

## Implementation Phases

### Phase 1 — Correct boundaries

- Remove the idea that Workflow Assistant is a trainable NPC from primary UI.
- Keep manifest/docs dataset tooling only as an optional internal docs-corpus maintenance panel.
- Rename current panel to `WorkflowDocsCorpusPanel` if retained.
- Add missing backend `/api/assistant/*` routes or remove dead UI calls until implemented.

### Phase 2 — Read-only assistant

- Implement `/api/assistant/chat` with:
  - resource guard
  - static docs retrieval
  - context collector
  - Ollama request with `keep_alive: 0s`
- No command execution yet.
- Support log/result analysis from existing APIs.

### Phase 3 — Artifact-aware diagnostics

Add specialized backend context endpoints:

- `/api/assistant/context/project-snapshot`
- `/api/assistant/context/job/:id`
- `/api/assistant/context/npc/:npcKey`
- `/api/assistant/context/run/:npcKey/:runId`
- `/api/assistant/context/quality/:npcKey/:technique`
- `/api/assistant/context/eval/:reportId`

### Phase 4 — Safe action proposals

- Assistant returns `ProposedAction[]` separately from markdown.
- UI renders action cards.
- User must click “Preview” then “Run”.
- Execution uses `/api/commands/start`, not arbitrary shell.

### Phase 5 — Comparison and improvement loop

- Add run comparison summaries.
- Add dataset failure clustering.
- Add feedback gap synthesis.
- Add suggested next experiment cards:
  - update primer
  - regenerate focused examples
  - sanitize strict canonical
  - run fast/release dataset-eval
  - train with selected preset
  - evaluate adapter on base model

### Phase 6 — Persistent assistant memory

Store only durable operational facts, not raw chat:

- known local base model path
- preferred assistant profile
- repeated failure signatures and fixes
- stable project conventions

## Acceptance Criteria

The assistant is ready when it can:

1. Explain exact current pipeline commands using current `ucore` flags.
2. Detect when training/eval/generation is running and pause LLM usage.
3. Read a failed job log and cite the exact error.
4. Read `quality_failures.json` and propose dataset/reference-doc fixes without lowering thresholds.
5. Compare two training runs using metrics and eval artifacts.
6. Recommend safe next steps for LLMUnity deployment.
7. Propose command payloads through schemas, not raw shell.
8. Unload its model before GPU-heavy pipeline jobs.
9. Avoid roleplaying or being treated as a Unity NPC.
10. Keep all recommendations aligned with the project goal: best local Unity NPC LoRA adapter workflow.
