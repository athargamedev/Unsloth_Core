# State-Enforced Pipeline 10x Reliability Plan

> For Hermes: Use subagent-driven-development skill to implement this plan task-by-task.

Goal: Convert Unsloth_Core from a script-driven NPC training workflow into a state-enforced, cache-aware, GPU-safe pipeline that prevents stale artifacts, reduces repeated judge/training work, and makes production decisions auditable.

Architecture: Keep `./ucore` as the operator entrypoint, but make it call a canonical DAG planner, artifact/content-addressed registry, judge result cache, and GPU/inference lifecycle service. The first implementation should be small and local-first: SQLite/DuckDB + JSONL compatibility + FastAPI health endpoints + tests. Do not replace working scripts; wrap them behind contracts, then migrate one stage at a time.

Tech Stack: Python, Pydantic, SQLite or DuckDB, FastAPI, existing `./ucore`, Ollama, llama.cpp/llama-server, Confident AI, W&B, Supabase/PipelineDB, pytest.

---

## 0. Report Analysis: What It Proves

### 0.1 Strong signals from the report

1. Confident AI Connections are useful for local/private evaluation.
   - The Docker agent acts as outbound WebSocket tunnel.
   - No public URL or inbound firewall rule is needed.
   - Local eval server must be running at `http://host.docker.internal:8765/eval/single` or equivalent.

2. The training stack must become contract-enforced, not advice-enforced.
   - Response-only loss masking must be required and verified.
   - LoRA alpha/rank should default to a stable `alpha = r` policy unless a named experiment says otherwise.
   - Dataset rows must carry usable grounding context/provenance, not just assistant text.

3. Dataset quality is now measurable but not yet structurally protected.
   - History Guide looks strong.
   - Chef Assistant is weak on concept fidelity and likely needs grounded regeneration.
   - Qwen 2.5 7B and Llama 3.1 8B agreement is useful, but it is not enough to skip cache/provenance controls.

4. 6GB VRAM is the main loop bottleneck.
   - Cold model starts can exceed default timeouts.
   - Judge/training concurrency must be actively managed.
   - Warm/unload behavior should be centralized, not scattered across scripts.

### 0.2 Risks found while checking current repo state

These are not criticisms; they are implementation hazards the plan must handle.

1. Some current state contradicts the report.
   - `etc/presets/fast-3b.yaml` already has `alpha: 16`, but `etc/npc-production-strategy.yaml` still has `lora_alpha: 32` for production and density repair profiles.
   - `etc/parameter-registry.yaml` still describes LoRA alpha as usually `2x lora_r`, which conflicts with the new stability rule.
   - `src/core/evaluation/quick_eval.py` still hardcodes `lora_alpha=32`.
   - Plan requirement: add config coherence tests before trusting the new defaults.

2. The repo already has partial DAG/registry pieces.
   - Tests exist in `tests/test_pipeline_dag_registry.py`.
   - `src/core/ops/run_registry.py`, `src/core/ops/workflow_hooks.py`, PipelineDB, history/registry commands, and `./ucore audit pipeline-plan` already exist.
   - Plan requirement: do not build another DAG system. Harden and connect the existing one.

3. Current active NPC scope must stay small.
   - Active NPCs are `history_guide` and `chef_assistant` only.
   - Marvel data can be used as a research/stress dataset, but should not become active production scope unless Andre explicitly reactivates it.

4. The new LLM grounding verifier and LLM check need cache and lifecycle controls.
   - `LLMSanityChecker` exists in `src/core/dataset/sanitize_dataset.py` and uses a 180s timeout.
   - `src/core/dataset/generate_dataset.py` has judge timeout paths and Ollama lifecycle hooks.
   - Without result caching and GPU state locks, deeper LLM verification can make the pipeline more expensive and flaky.

### 0.3 Structural target

The 10x upgrade is not one feature. It is five contracts enforced together:

1. State contract: every stage declares inputs, outputs, hashes, and readiness.
2. Training contract: every train run validates dataset gate, response masking, LoRA params, and VRAM policy before starting.
3. Judge contract: every judge call is content-addressed, cached, model-versioned, and replayable.
4. GPU contract: every local model operation goes through a lease/warm/unload manager.
5. Operator contract: CLI, dashboard, Confident, W&B, and local artifacts all point to the same run family.

---

## 1. North-Star Architecture

### 1.1 Target workflow

Operator asks for a target, not a command sequence:

```bash
./ucore target evaluate --npc-key chef_assistant --profile npc-production-grounded
```

The system answers:

1. Current artifact graph.
2. Fresh/stale/missing states.
3. Next required stage.
4. Estimated GPU/judge cost.
5. Safe command plan.
6. Optional execution with resume.

Example output shape:

```json
{
  "npc_key": "chef_assistant",
  "profile": "npc-production-grounded",
  "target_stage": "evaluate",
  "ready": false,
  "next_required_stage": "generate",
  "blockers": [
    {"stage": "generate", "reason": "reference_doc_hash changed since latest train.jsonl"},
    {"stage": "sanitize", "reason": "latest clean hash does not match latest raw hash"},
    {"stage": "dataset_eval", "reason": "no passing release gate for clean hash"}
  ],
  "plan": ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate"],
  "cache_hits": {"judge_rows": 0, "dataset_rows": 0},
  "gpu_policy": {"mode": "exclusive_train", "judge_model_loaded": false}
}
```

### 1.2 Canonical stage DAG

Canonical production DAG:

```text
validate_spec
  -> generate_dataset
  -> sanitize_dataset
  -> dataset_quality_gate
  -> train_adapter
  -> export_lora_gguf
  -> runtime_eval_base_plus_lora
  -> feedback_decision
  -> promote_or_repair
```

Optional side branches:

```text
generate_dataset -> confident_goldens -> confident_push -> remote_eval
train_adapter -> wandb_metrics
runtime_eval -> wandb_eval_artifacts
runtime_eval -> confident_remote_eval
feedback_decision -> repair_dataset -> sanitize_dataset
```

### 1.3 Canonical IDs

Every artifact must carry these fields:

```text
npc_key
profile
technique
stage
run_id
artifact_type
path
sha256
input_hashes
spec_sha256
reference_doc_sha256
dataset_raw_sha256
dataset_clean_sha256
judge_provider
judge_model
base_model
adapter_path
lora_r
lora_alpha
train_on_responses_only
quantization
created_at
producer_command
```

### 1.4 Production promotion rule

A GGUF adapter is not production-ready unless one manifest proves:

1. Dataset was generated with production-approved grounded workflow.
2. `template_allowed == false` for production profile.
3. Sanitized dataset is derived from current raw hash.
4. Quality gate judged current clean hash.
5. Training used a passing gate hash.
6. Training config used response-only masking.
7. Training config used approved LoRA stability policy or named experiment override.
8. Export was from the same trained run.
9. Runtime eval used base+LoRA, not standalone adapter.
10. Feedback decision says promote/ready, not inspect/repair/escalate.

---

## 2. Phase Plan Overview

### Phase 1A: Coherence Freeze and Safety Audit

Purpose: Stop new drift while another session runs existing phase 1 work.

Deliverables:
- Config coherence tests for LoRA alpha, response masking, profile flags, and template production ban.
- CLI `./ucore audit config-coherence` or extension to `./ucore audit check`.
- Report showing all current contradictions.

Why first:
- The report says alpha was standardized, but current checked files still contain `lora_alpha: 32` in strategy profiles. This must be detected automatically.

### Phase 1B: Strengthen Existing DAG/Registry Instead of Rebuilding

Purpose: Make artifact freshness impossible to ignore.

Deliverables:
- Registry records all canonical stage artifacts with input hashes.
- DAG planner detects stale downstream artifacts when upstream hash changes.
- `./ucore audit pipeline-plan` becomes the source for next-stage decisions.

### Phase 2: Judge Delta Cache

Purpose: Stop re-judging identical content.

Deliverables:
- SQLite/DuckDB judge cache keyed by row content + reference context + rubric + judge model + prompt version.
- Dataset-eval, sanitizer `--llm-check`, generate grounding verifier, and multi-judge study all use the same cache.
- Cross-judge audit can re-evaluate only low/changed rows.

### Phase 3: GPU/Inference Orchestrator

Purpose: Stop cold-start loops and VRAM fights.

Deliverables:
- Local FastAPI inference manager with health, warm, unload, lease, queue, and generation/judge endpoints.
- Training acquires exclusive GPU lease; judge work pauses/unloads automatically.
- Confident AI local eval endpoint runs through this service.

### Phase 4: Contract-First NPC Components

Purpose: Make NPC specs reusable and testable.

Deliverables:
- Pydantic component models: `IdentityContract`, `ToneContract`, `GroundingContract`, `RefusalContract`, `RuntimeConstraintContract`, `DatasetDistributionContract`.
- Existing JSON specs remain supported through migration adapter.
- Component-level tests produce targeted generation/eval rows.

### Phase 5: Operator Control Plane and Dashboard Truthfulness

Purpose: Make CLI/dashboard/Confident/W&B show one truth.

Deliverables:
- Dashboard reads DAG plan + registry + process state, not guessed cards.
- Every CLI command schema appears in dashboard command modal.
- Confident/W&B links are recorded in manifests and reports.

### Phase 6: Self-Improving Repair Loop

Purpose: Turn failures into bounded repairs without infinite loops.

Deliverables:
- Feedback decisions write explicit repair plans.
- Chef Assistant concept-fidelity repair becomes the first production benchmark.
- Anti-loop escalation routes shared failures to shared prompts/presets.

---

## 3. Phase 1A Detailed Plan: Coherence Freeze and Safety Audit

### Task 1A.1: Add config coherence model

Objective: Represent project-wide training/dataset invariants in one testable module.

Files:
- Create: `src/core/ops/config_coherence.py`
- Test: `tests/test_config_coherence.py`

Core invariants:

```python
APPROVED_PRODUCTION_TECHNIQUES = {"ollama", "docs", "openai", "anthropic"}
SMOKE_ONLY_TECHNIQUES = {"template"}

REQUIRED_TRAINING_INVARIANTS = {
    "train_on_responses_only": True,
    "packing_for_6gb": False,
}

LORA_STABILITY_POLICY = {
    "default": "alpha_eq_r",
    "allow_override_if_named_experiment": True,
}
```

Checks:

1. All production profiles have `dataset.template_allowed: false`.
2. Production profiles do not use `technique: template`.
3. Production profiles use `training.lora_alpha == training.lora_r`, unless `metadata.experimental_lora_scaling: true` exists.
4. `etc/presets/*.yaml` LoRA alpha equals rank unless preset is explicitly marked experimental.
5. `etc/parameter-registry.yaml` tooltip and default text do not recommend `alpha = 2r` as normal production behavior.
6. Training default config has `train_on_responses_only: true`.
7. Any hardcoded `lora_alpha=32` in quick eval/research code is tagged smoke-only or replaced.

Verification:

```bash
pytest tests/test_config_coherence.py -q
python -m compileall src/core/ops/config_coherence.py
```

Expected:
- Initial RED should catch current `npc-production-grounded.training.lora_alpha: 32` and `npc-density-repair.training.lora_alpha: 32`.
- GREEN after config fixes.

### Task 1A.2: Wire coherence audit into CLI

Objective: Make safety checks operator-visible before expensive runs.

Files:
- Modify: `src/cli/ucore`
- Modify or Create: `src/core/ops/audit.py`
- Test: `tests/test_config_coherence.py`

Command:

```bash
./ucore audit config-coherence --json
```

Output shape:

```json
{
  "ok": false,
  "failures": [
    {
      "file": "etc/npc-production-strategy.yaml",
      "path": "profiles.npc-production-grounded.training.lora_alpha",
      "expected": 16,
      "actual": 32,
      "reason": "production LoRA alpha must equal rank"
    }
  ]
}
```

Verification:

```bash
./ucore audit config-coherence --json
./ucore audit check
```

### Task 1A.3: Fix current coherence violations

Objective: Align actual configs with the report.

Files likely modified:
- `etc/npc-production-strategy.yaml`
- `etc/parameter-registry.yaml`
- `etc/presets/premium-3b.yaml`
- `etc/presets/remote-3b-quality.yaml`
- `etc/presets/quality-1.7b.yaml`
- `src/core/evaluation/quick_eval.py`

Rules:
- Production/default presets: `alpha = r`.
- Experimental aggressive presets may keep higher alpha only if explicitly named and tagged, for example:

```yaml
metadata:
  experimental_lora_scaling: true
  reason: "Ablation only; not production default"
```

Verification:

```bash
pytest tests/test_config_coherence.py -q
./ucore audit config-coherence --json
```

Done when:
- Audit is green.
- Any remaining alpha/rank mismatch is explicitly experimental.

---

## 4. Phase 1B Detailed Plan: Artifact DAG Hardening

### Task 1B.1: Add input hash lineage to artifact records

Objective: Make staleness detectable, not implied.

Files:
- Modify: `scripts/ops/artifact_registry.py` if still the active module
- Or Modify: `src/core/ops/canonical_artifacts.py` / `src/core/ops/workflow_hooks.py` if current source of truth moved
- Test: `tests/test_pipeline_dag_registry.py`

Add fields:

```json
{
  "input_hashes": {
    "spec": "sha256:...",
    "reference_doc": "sha256:...",
    "dataset_raw": "sha256:...",
    "dataset_clean": "sha256:...",
    "quality_summary": "sha256:..."
  },
  "producer_command": "./ucore sanitize ...",
  "profile": "npc-production-grounded"
}
```

Stage lineage:

- `generate`: inputs = spec, reference_doc, generation profile, generator model/prompt version.
- `sanitize`: inputs = dataset_raw, sanitizer config, spec.
- `dataset_eval`: inputs = dataset_clean, judge model, rubric version, reference_doc.
- `train`: inputs = dataset_clean, quality_summary, training config, base model.
- `export`: inputs = adapter checkpoint, export config.
- `evaluate`: inputs = GGUF adapter, base model, eval prompt set, judge config.

Verification:

```bash
pytest tests/test_pipeline_dag_registry.py -q
```

### Task 1B.2: Teach DAG stale-vs-missing distinction

Objective: Report exactly why a downstream artifact cannot be reused.

Files:
- Modify: `scripts/ops/pipeline_dag.py` or active DAG module
- Test: `tests/test_pipeline_dag_registry.py`

States:

```text
ready       artifact exists and input hashes match
missing     required artifact absent
stale       artifact exists but upstream input hash changed
inconclusive artifact exists but lacks lineage metadata
blocked     prior stage missing/stale/inconclusive
```

Example:

```json
{
  "stage": "dataset_eval",
  "state": "stale",
  "reason": "dataset_clean sha changed after latest quality_summary"
}
```

Verification test:
- Create raw file v1 -> clean v1 -> quality v1.
- Modify clean file to v2.
- Assert `train` blocked because `quality_summary` is stale, not missing.

### Task 1B.3: Block production train on stale/missing gate by default

Objective: Move `--allow-ungated-dataset` from warning culture to explicit unsafe override.

Files:
- Modify: `src/core/training/train.py`
- Modify: `src/cli/ucore`
- Test: `tests/test_training_gate_contract.py` or existing workflow tests

Rule:
- `./ucore train ...` checks DAG readiness for `train` before starting.
- If no passing quality gate exists for current clean hash, abort.
- `--allow-ungated-dataset` remains, but output must label run `smoke_only: true` in metadata and registry.

Verification:

```bash
pytest tests/test_training_gate_contract.py -q
./ucore train data/npcs/specs/chef_assistant.json --technique ollama --preset fast-3b
```

Expected if gate missing:

```text
Blocked: no fresh passing dataset-eval for current train_clean.jsonl
Next: ./ucore dataset-eval data/npcs/specs/chef_assistant.json --technique ollama --mode release
```

### Task 1B.4: Add `target` command as wrapper around existing DAG

Objective: Let operators request outcomes.

Files:
- Modify: `src/cli/ucore`
- Create: `src/core/orchestration/target_runner.py`
- Test: `tests/test_target_runner.py`

Commands:

```bash
./ucore target plan --npc-key chef_assistant --profile npc-production-grounded --target-stage evaluate
./ucore target run --npc-key chef_assistant --profile npc-production-grounded --target-stage dataset_eval --dry-run
./ucore target run --npc-key chef_assistant --profile npc-production-grounded --target-stage evaluate --resume
```

Initial scope:
- `plan` only in first PR.
- `run --dry-run` in second PR.
- Real execution after DAG and safety checks are stable.

---

## 5. Phase 2 Detailed Plan: Judge Delta Cache

### Task 2.1: Define judge cache schema

Objective: Cache expensive LLM judge outputs by exact inputs.

Files:
- Create: `src/core/ops/judge_cache.py`
- Test: `tests/test_judge_cache.py`

SQLite table:

```sql
CREATE TABLE IF NOT EXISTS judge_results (
  cache_key TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  judge_provider TEXT NOT NULL,
  judge_model TEXT NOT NULL,
  judge_model_digest TEXT,
  rubric_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  input_sha256 TEXT NOT NULL,
  context_sha256 TEXT NOT NULL,
  expected_sha256 TEXT,
  actual_sha256 TEXT NOT NULL,
  npc_key TEXT,
  category TEXT,
  concept TEXT,
  score REAL,
  pass INTEGER,
  result_json TEXT NOT NULL,
  latency_ms INTEGER,
  error TEXT
);
```

Cache key:

```text
sha256(judge_provider|judge_model|judge_model_digest|rubric_id|prompt_version|input|context|expected|actual)
```

Default path:

```text
var/cache/judge_results.sqlite
```

### Task 2.2: Add cache to sanitizer `--llm-check`

Objective: Avoid re-checking identical rows during sanitize.

Files:
- Modify: `src/core/dataset/sanitize_dataset.py`
- Test: `tests/test_sanitize_llm_cache.py`

Rules:
- Use cache by default.
- Add `--no-judge-cache` to bypass.
- Add `--judge-cache-path` for tests/custom runs.
- Record cache hit/miss counts in sanitizer manifest.

Verification:

```bash
pytest tests/test_sanitize_llm_cache.py -q
./ucore sanitize data/datasets/chef_assistant/ollama/train.jsonl --output data/datasets/chef_assistant/ollama/train_clean.jsonl --llm-check
```

Expected manifest fields:

```json
{
  "llm_check": {
    "cache_hits": 87,
    "cache_misses": 12,
    "judge_model": "qwen2.5:7b"
  }
}
```

### Task 2.3: Add cache to dataset-eval and grounding verifier

Objective: Make all judge layers share the same memory.

Files:
- Modify: `src/core/dataset/dataset_eval.py`
- Modify: `src/core/dataset/generate_dataset.py`
- Test: `tests/test_dataset_eval_judge_cache.py`

Rules:
- Cache rows by rubric/prompt version.
- A generation grounding check and a release quality gate are different rubrics, so they do not collide.
- If `--disable-cache` exists for Confident/release mode, decide whether it disables only DeepEval internal cache or also local judge cache. Prefer explicit flags:
  - `--disable-deepeval-cache`
  - `--disable-local-judge-cache`

### Task 2.4: Add cross-judge audit command

Objective: Re-review only uncertain/low rows with a second judge.

Files:
- Create: `src/core/research/cross_judge_audit.py`
- Modify: `src/cli/ucore`
- Test: `tests/test_cross_judge_audit.py`

Command:

```bash
./ucore judge-audit data/datasets/chef_assistant/ollama/train_clean.jsonl \
  --primary qwen2.5:7b \
  --secondary llama3.1:8b \
  --only-below 0.80 \
  --cache
```

Output:
- disagreement count
- low-confidence rows
- concepts needing repair
- cached vs newly judged counts

---

## 6. Phase 3 Detailed Plan: GPU/Inference Orchestrator

### Task 3.1: Create model manager API skeleton

Objective: One local service owns model warm/unload/queue state.

Files:
- Create: `src/core/inference/model_manager.py`
- Create: `src/core/inference/server.py`
- Create: `tests/test_model_manager.py`

Endpoints:

```text
GET  /health
GET  /state
POST /lease/acquire
POST /lease/release
POST /models/warm
POST /models/unload
POST /judge/chat
POST /eval/single
```

State model:

```python
class GpuLease(BaseModel):
    owner: str
    purpose: Literal["judge", "generate", "train", "eval"]
    exclusive: bool
    acquired_at: datetime
    expires_at: datetime | None
```

Rules:
- Training gets exclusive lease.
- Judge/generate can share only if policy allows and VRAM free threshold is met.
- If exclusive lease requested, unload Ollama judge model first.

### Task 3.2: Add GPU state probes

Objective: Make decisions from actual local state.

Files:
- Create: `src/core/inference/gpu_state.py`
- Test: `tests/test_gpu_state.py`

Probe sources:
- `nvidia-smi --query-gpu=memory.used,memory.free,memory.total`
- `ollama ps`
- known llama-server PIDs/ports

Output shape:

```json
{
  "gpu": {"total_mb": 6144, "free_mb": 4810, "used_mb": 1334},
  "ollama": {"loaded_models": ["qwen2.5:7b"]},
  "llama_server": {"ports": [8765], "pids": [1234]},
  "recommended_action": "safe_to_judge"
}
```

### Task 3.3: Add warm model command

Objective: Replace ad hoc `ollama run model "hi"` with a measured warmup.

Files:
- Modify: `src/cli/ucore`
- Modify: `src/core/inference/server.py`
- Test: `tests/test_model_manager.py`

Command:

```bash
./ucore models warm --role judge --model qwen2.5:7b --timeout 180
./ucore models state --json
./ucore models unload --role judge
```

### Task 3.4: Route Confident AI local eval endpoint through manager

Objective: Make the tunnel useful without manual server uncertainty.

Files:
- Modify/Create: `src/core/inference/server.py`
- Modify: `infra/confident-agent/compose.yaml` if needed
- Test: `tests/test_confident_local_eval_endpoint.py`

Endpoint payload:

```json
{
  "npc_key": "chef_assistant",
  "input": "How do I stop chicken from drying out?",
  "context": ["...reference snippet..."],
  "adapter": "artifacts/exports/chef_assistant/chef_assistant-lora-f16.gguf",
  "base_model": ".models/llama-3.2-3b-instruct-q4_k_m.gguf"
}
```

Response:

```json
{
  "actualOutput": "...",
  "retrieval_context": ["..."],
  "metadata": {
    "npc_key": "chef_assistant",
    "base_model": "...",
    "adapter": "...",
    "cache_hit": false,
    "latency_ms": 8421
  }
}
```

### Task 3.5: Make training/eval use GPU leases

Objective: Prevent judge/train simultaneous OOM.

Files:
- Modify: `src/core/training/train.py`
- Modify: `src/core/evaluation/evaluate.py`
- Modify: `src/core/dataset/dataset_eval.py`
- Test: `tests/test_gpu_lease_integration.py`

Rules:
- `train.py` requests exclusive lease.
- `dataset_eval.py` requests judge lease.
- `evaluate.py` requests eval lease and dynamic port.
- If lease unavailable, command prints blocker and next safe action.

---

## 7. Phase 4 Detailed Plan: Contract-First NPC Components

### Task 4.1: Define component schemas

Objective: Stop growing one giant spec and scattered if/else logic.

Files:
- Create: `src/core/specs/components.py`
- Test: `tests/test_npc_components.py`

Components:

```python
class FactualKnowledge(BaseModel):
    reference_doc_path: Path
    required_topics: list[str]
    forbidden_claims: list[str] = []
    retrieval_required: bool = True

class ToneGuardrails(BaseModel):
    voice: str
    sentence_limit: int
    character_limit: int
    forbidden_style: list[str]

class RefusalLogic(BaseModel):
    out_of_scope_policy: str
    redirect_template: str
    unsafe_topics: list[str]

class DatasetDistribution(BaseModel):
    category_targets: dict[str, int]
    density_targets: dict[str, WordRange]
```

### Task 4.2: Add migration adapter from current JSON specs

Objective: Keep all current specs working.

Files:
- Create: `src/core/specs/adapter.py`
- Modify: `src/core/dataset/validate_subject_spec.py`
- Test: `tests/test_npc_spec_adapter.py`

Rules:
- Existing `data/npcs/specs/<npc>.json` loads into components.
- Missing component fields produce actionable validation errors.
- Component validation does not train/generate.

### Task 4.3: Add component-level test case generation

Objective: Test refusal/identity/grounding without full dataset generation.

Files:
- Create: `src/core/specs/component_tests.py`
- Modify: `src/cli/ucore`
- Test: `tests/test_component_tests.py`

Command:

```bash
./ucore spec test-components data/npcs/specs/chef_assistant.json --json
```

Output:

```json
{
  "identity": "pass",
  "refusal": "pass",
  "grounding": "fail",
  "failures": [
    {"component": "grounding", "reason": "Food safety topic lacks primer section"}
  ]
}
```

### Task 4.4: Reusable shared components

Objective: Share common contract logic between NPCs without copy-paste.

Files:
- Create: `data/npcs/components/common_unity_runtime.yaml`
- Create: `data/npcs/components/common_grounded_teaching.yaml`
- Modify: spec loader
- Test: `tests/test_npc_components.py`

Rule:
- Specs can include components by reference.
- Resolved spec manifest records component hashes.

---

## 8. Phase 5 Detailed Plan: Operator Control Plane

### Task 5.1: Dashboard reads pipeline plan API

Objective: Frontend shows real readiness.

Files:
- Modify: `src/dashboard/unity-npc-llm-training-dashboard/server.ts`
- Modify frontend route/component files under dashboard app
- Test: dashboard backend/unit tests

API:

```text
GET /api/pipeline/plan?npc_key=chef_assistant&profile=npc-production-grounded&target_stage=evaluate
```

Response: same as `./ucore target plan`.

### Task 5.2: External process reconciliation

Objective: CLI-started jobs appear in dashboard.

Sources:
- `.pipeline/runs.jsonl`
- `.pipeline/runs/<run_id>/meta.json`
- PipelineDB if available
- filesystem artifact registry

Rule:
- Dashboard must not infer progress from random log lines.
- It should use stage markers, run registry, and terminal status.

### Task 5.3: Command schema parity

Objective: Every `./ucore` feature is selectable from UI.

Files:
- `etc/parameter-registry.yaml`
- dashboard command schema API
- `src/cli/ucore`

Checks:
- `./ucore --help` command list matches `/api/available-commands`.
- All production-critical flags appear in `/api/command-schemas`:
  - `--strategy-profile`
  - `--train-on-responses`
  - `--lora-alpha`
  - `--quantization`
  - `--confident`
  - `--wandb`
  - `--judge-provider`
  - `--judge-model`
  - `--base-model`
  - `--lora-weight`

### Task 5.4: One run-family report

Objective: Investor/operator reports point to one coherent chain.

Files:
- Modify report writers in evaluation/training/export modules.
- Modify PipelineDB insert paths.

Required report block:

```json
{
  "run_family_id": "20260604_chef_assistant_grounded_001",
  "dataset_raw": "...",
  "dataset_clean": "...",
  "quality_gate": "...",
  "training_run": "...",
  "gguf_adapter": "...",
  "eval_report": "...",
  "feedback_json": "...",
  "wandb_url": "...",
  "confident_test_run_id": "..."
}
```

---

## 9. Phase 6 Detailed Plan: Chef Assistant as First 10x Benchmark

### Task 6.1: Build Chef Assistant current-state bundle

Objective: Make the generic-advice problem reproducible.

Command:

```bash
./ucore target plan --npc-key chef_assistant --profile npc-production-grounded --target-stage evaluate --write artifacts/plans/chef_assistant_current_plan.json
./ucore audit config-coherence --json > artifacts/reports/config_coherence_chef_assistant.json
```

Collect:
- latest raw/clean dataset hashes
- latest quality report
- latest feedback JSON
- current spec hash
- current primer hash
- latest trained adapter path, if any

### Task 6.2: Regenerate with grounding verifier and judge cache

Objective: Fix low concept fidelity without wasting judge calls.

Command shape:

```bash
./ucore target run --npc-key chef_assistant --profile npc-production-grounded --target-stage dataset_eval --resume
```

Must enforce:
- no template production data
- retrieval_context present
- judge cache enabled
- warm judge model before local LLM checks
- batch/concurrency 1 on local 6GB unless manager says safe

### Task 6.3: Train/export only after gate freshness is green

Command shape:

```bash
./ucore target run --npc-key chef_assistant --profile npc-production-grounded --target-stage export --resume
```

Must record:
- `train_on_responses_only: true`
- `lora_r: 16`
- `lora_alpha: 16`
- `packing: false`
- `max_seq_len: 512`
- W&B run URL if enabled
- GGUF adapter path

### Task 6.4: Runtime eval base+LoRA and feedback classification

Command shape:

```bash
./ucore target run --npc-key chef_assistant --profile npc-production-grounded --target-stage evaluate --resume
./ucore feedback artifacts/eval/results/feedback/chef_assistant.json --strategy-profile npc-production-grounded --json
```

Promotion criteria:
- Candidate win rate >= profile ready threshold.
- No major weak concept cluster.
- Candidate answer density not below threshold.
- Confident/W&B/local report all point to same run family.

---

## 10. Acceptance Criteria

### Reliability

1. A production train cannot start on stale/missing dataset gate unless `--allow-ungated-dataset` is used.
2. Any ungated run is marked smoke-only in registry and reports.
3. `./ucore audit config-coherence` catches LoRA alpha/rank drift.
4. `./ucore audit pipeline-plan` distinguishes missing/stale/inconclusive artifacts.
5. Every deployable GGUF has a manifest that traces back to dataset/spec/reference hashes.

### Efficiency

1. Re-running LLM check on unchanged rows shows >80% judge cache hit rate after first run.
2. Re-running target plan on unchanged artifacts skips generate/sanitize/gate/train/export.
3. Judge warmup is explicit and measured.
4. Training unloads judge models or obtains exclusive GPU lease before model load.
5. Cross-judge audit reviews only low/changed rows by default.

### Quality

1. Chef Assistant concept fidelity improves from the reported 4.6/10 target area to passing release gate.
2. Dataset rows include `retrieval_context` or equivalent source context provenance.
3. Response-only masking is verified in training config and logged.
4. LoRA alpha/rank policy is visible in training report.
5. Confident insights route failures to components, not vague advice.

### Operator UX

1. Dashboard and CLI show same next action.
2. CLI-started jobs appear in dashboard history.
3. Every production-critical CLI flag has dashboard command schema coverage.
4. Reports show local artifact paths plus W&B/Confident links if enabled.

---

## 11. Immediate Next 3 Actions

1. Add and run `tests/test_config_coherence.py` to catch current alpha/rank and profile drift.
2. Fix `etc/npc-production-strategy.yaml` production `lora_alpha` from 32 to 16, or explicitly mark as experimental if Andre wants the old aggressive setting preserved for ablations.
3. Extend existing DAG registry tests to detect stale artifacts by input hash, then wire train blocking to that result.

---

## 12. Resume Protocol

Current phase status:
- Existing phase 1 is running in another session.
- This plan should not duplicate that work blindly.
- First implementation should start with Phase 1A because it is safe, fast, and catches report-vs-repo contradictions.

Next phase entry command after implementation starts:

```bash
pytest tests/test_config_coherence.py tests/test_pipeline_dag_registry.py -q
./ucore audit config-coherence --json
./ucore audit pipeline-plan --npc-key chef_assistant --technique ollama --target-stage train --json
```

Done-when for Phase 1A:
- Config coherence test passes.
- Audit command passes.
- Production profiles use stable LoRA defaults or explicit experimental tags.

Done-when for Phase 1B:
- Pipeline plan detects stale downstream artifacts from changed upstream hashes.
- Production train blocks on stale/missing gate.
- Smoke override labels artifacts correctly.

---

## 13. Implementation Notes for Subagents

Use these task lanes:

1. Safety/config lane:
   - `config_coherence.py`
   - `tests/test_config_coherence.py`
   - strategy/preset/parameter registry fixes

2. DAG/registry lane:
   - artifact input hashes
   - stale-state detection
   - train gate blocking

3. Judge cache lane:
   - `judge_cache.py`
   - sanitizer integration
   - dataset-eval integration

4. GPU manager lane:
   - model manager skeleton
   - warm/unload commands
   - Confident local endpoint

5. Dashboard lane:
   - plan API
   - command schema parity
   - external process reconciliation

Each lane must add tests before code, run targeted tests, and report only real output.
