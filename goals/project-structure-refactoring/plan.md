# Plan: Project Structure & Workflow Refactoring

## Goal
Restructure the project into a professional, self-documenting layout with clean separation of artifacts (datasets → outputs → exports → eval), generation-technique-aware dataset directories, TensorBoard-integrated evaluations, run ID experiment tracking, workflow documentation for every pipeline stage, and a modern frontend for managing the entire training lifecycle.

---

## Context & Decisions

| Decision | Rationale | Source |
|----------|-----------|--------|
| Keep YAML configs as model-size templates | Configs define model/preset combos; `output_dir` is NPC-specific, overridden at CLI | Original approved plan |
| Strip hardcoded `output_dir` from YAML defaults | Prevent accidental overwrites; force NPC-based output via CLI | Original approved plan |
| Separate datasets by technique | Ollama, template, NotebookLM produce fundamentally different quality; OLLAMA_WORKFLOW.md documents the distinction | Original approved plan annotation #3 |
| Integrate TensorBoard into eval reports with HTML+plots | Professional eval needs loss curves, not just text; `evaluate.py --training-metrics` already parses TB logs | Original approved plan annotation #2 |
| Align exports with Unity `StreamingAssets/Models/` | `deploy_to_unity.py` copies GGUF to `Assets/StreamingAssets/Models/` + writes manifest | Original approved plan |
| Add run IDs for experiment tracking | Enable training same NPC with different settings and comparing results | User expansion |
| Add workflow docs for every pipeline stage | Project becomes self-documenting, matching OLLAMA_WORKFLOW.md pattern | User expansion |
| Build professional frontend | HTMX + Alpine.js + Chart.js for lightweight SPA that manages the full lifecycle | User expansion |

---

## Solution Overview

Transform Unsloth_Core into a **professional ML training platform** with:

### Current → Target Directory Structure

```
CURRENT:                              TARGET:
subjects/{npc_key}.json          →    subjects/{npc_key}.json  (unchanged)

datasets/                         →    datasets/{npc_key}/
  {npc_key}.jsonl                      {technique}/  (notebooklm|ollama|template)
  {npc_key}_validation.jsonl           train.jsonl
  {npc_key}_ollama.jsonl               validation.jsonl
  {npc_key}_ollama_validation.jsonl

outputs/{npc_key}/                →    outputs/{npc_key}/  (adapters + checkpoints ONLY)
  adapter_model.safetensors             adapter_model.safetensors
  adapter_config.json                   adapter_config.json
  {npc_key}-lora.f16.gguf  ← REMOVE    checkpoint-N/
  checkpoint-N/                         runs/
  runs/                                 runs/{run_id}/  (NEW: run IDs)

exports/ (empty)                  →    exports/{npc_key}/  (GGUF ONLY)
                                       {npc_key}-{model_short}-{quant}.gguf
                                       manifest.json

eval/ (empty)                     →    eval/
                                       training-metrics/{npc_key}.yaml
                                       reports/{npc_key}/eval_{date}.md (+ .html)
                                       comparisons/{npc_key}_vs_{baseline}_{date}.md
                                       results/eval_results.jsonl

_config/                          →    _config/paths.py  (shared path helpers, ALREADY EXISTS)

configs/base.yaml + presets/*.yaml →   configs/presets/  (YAML-only presets)
                                       configs/models/  (model arch configs)

docs/OLLAMA_WORKFLOW.md only      →    docs/NOTEBOOKLM_WORKFLOW.md
                                       docs/TEMPLATE_WORKFLOW.md
                                       docs/TRAINING_WORKFLOW.md
                                       docs/EVALUATION_WORKFLOW.md
```

### Artifact Lifecycle
```
subjects/{npc_key}.json
        │
        ▼
datasets/{npc_key}/{technique}/   ← Raw material, regenerable
  train.jsonl + validation.jsonl
        │
        ▼
outputs/{npc_key}/                ← Intermediate, can be recreated
  runs/{run_id}/
    adapter + frozen config + metrics + TB logs
  latest -> runs/{run_id}
  best -> runs/{run_id}
        │
        ▼
exports/{npc_key}/                ← Final, deployable to Unity StreamingAssets
  {npc_key}-{model_short}-{quant}.gguf
  manifest.json
        │
        ▼
eval/reports/{npc_key}/           ← Quality evidence (markdown + HTML)
eval/comparisons/                 ← Side-by-side comparisons
```

---

## Slices & Details

### Slice 1: Workflow Documentation [PENDING]

Create 4 new workflow docs following the exact style of `docs/OLLAMA_WORKFLOW.md`:

| Doc | Content |
|-----|---------|
| `NOTEBOOKLM_WORKFLOW.md` | NotebookLM dataset generation: research queries, API integration, output format, validation split |
| `TEMPLATE_WORKFLOW.md` | Template-based fallback generation: categories, concept pool, multi-turn logic |
| `TRAINING_WORKFLOW.md` | Unified training pipeline: presets, model selection, run IDs, export, troubleshooting |
| `EVALUATION_WORKFLOW.md` | Evaluation & comparison: TensorBoard metrics, side-by-side, LLM judge, HTML reports |

Each doc must include: architecture diagram/overview, usage commands, flag reference, comparison table (old vs new), and troubleshooting section.

---

### Slice 2: Config & Preset System [PENDING]

**2.1 Strip hardcoded `output_dir` from YAML configs**
- `configs/lora-sft-fast-1.7b.yaml`: `output_dir: outputs/fast-1.7b` → `output_dir: outputs/default`
- `configs/lora-sft-fast-3b.yaml`: `output_dir: outputs/fast-3b` → `output_dir: outputs/default`
- `configs/lora-sft-quality-1.7b.yaml`: `output_dir: outputs/quality-1.7b` → `output_dir: outputs/default`
- `configs/lora-sft-safe-any.yaml`: `output_dir: outputs/safe-any` → `output_dir: outputs/default`

**2.2 Create `configs/presets/` directory**
- Move ALL preset definitions from train.py PRESETS dict into YAML files
- Each preset YAML references `lora-sft-base.yaml` as the base
- Presets: `smoke.yaml`, `fast-0.5b.yaml`, `fast-1.7b.yaml`, `fast-3b.yaml`, `quality-1.7b.yaml`, `safe-any.yaml`

**2.3 Restructure configs**
- `configs/models/` — model architecture JSONs (moved from `configs/base_configs/`)
- `configs/presets/` — training presets
- `configs/lora-sft-base.yaml` — shared base config (unchanged)

**2.4 Remove PRESETS dict from train.py**
- Load presets from `configs/presets/*.yaml` instead
- `--show-presets` still works, now reads from filesystem

---

### Slice 3: Dataset Directory Restructure [PENDING]

**3.1 Technique-aware subdirectories**

Current:
```
datasets/
  chemistry_instructor.jsonl
  chemistry_instructor_validation.jsonl
  chemistry_instructor_ollama.jsonl
  chemistry_instructor_ollama_validation.jsonl
  bible_instructor.jsonl
  bible_instructor_validation.jsonl
```

Target:
```
datasets/
  chemistry_instructor/
    notebooklm/
      train.jsonl
      validation.jsonl
    ollama/
      train.jsonl
      validation.jsonl
    template/
      train.jsonl
      validation.jsonl
  bible_instructor/
    notebooklm/
      train.jsonl
      validation.jsonl
  ... (repeat for each NPC)
```

**3.2 Update `scripts/generate_dataset.py`**
- Write to `datasets/{npc_key}/{technique}/` (e.g., `--technique ollama` → ollama/)
- Infer technique from CLI: `--ollama` → `ollama/`, else `notebooklm/`
- Auto-detect existing technique dirs for validation split

**3.3 Update validation path logic**
- Replace `{data_path}_validation.jsonl` suffix trick with explicit `validation.jsonl` lookup in the same technique directory
- `scripts/train.py`: auto-detect dataset at `datasets/{npc_key}/{technique}/train.jsonl`
- `scripts/evaluate.py`: find validation set at `datasets/{npc_key}/{technique}/validation.jsonl`

---

### Slice 4: Experiment Tracking with Run IDs [PENDING]

**4.1 Run ID format**
`{YYYYMMDD}_{preset_name}_{sequential_number}` — e.g., `20260512_fast-3b_001`
- Sequential numbering resets daily per NPC
- Run ID stored in training config frozen copy

**4.2 Output structure**
```
outputs/{npc_key}/
├── runs/
│   ├── 20260512_fast-3b_001/
│   │   ├── adapter_model.safetensors
│   │   ├── adapter_config.json
│   │   ├── config.yaml              # Frozen copy of full training config
│   │   ├── trainer_state.json
│   │   ├── metrics.json             # Extracted training/eval metrics
│   │   └── runs/                    # TensorBoard event logs
│   ├── 20260512_quality-1.7b_001/
│   └── 20260512_fast-3b_002/
├── latest -> runs/20260512_fast-3b_001   # Symlink to latest run
└── best -> runs/20260512_quality-1.7b_001 # Symlink to best run (by eval loss)
```

**4.3 Update `scripts/train.py`**
- Generate run ID at training start
- Create `outputs/{npc_key}/runs/{run_id}/` directory
- Copy config to `config.yaml` inside run dir
- Extract metrics to `metrics.json` after training
- Create/update `latest` symlink
- Maintain backward compat: `outputs/{npc_key}/adapter_model.safetensors` still exists (or use symlink)

**4.4 Update `_config/paths.py`**
- Add `run_dir(npc_key, run_id)` → `outputs/{npc_key}/runs/{run_id}/`
- Add `latest_run_dir(npc_key)` → resolve `outputs/{npc_key}/latest` symlink
- Keep all existing path functions for backward compat

---

### Slice 5: Output → Export → Eval Restructure [PENDING]

**5.1 Clean separation**

**Outputs** (adapters + checkpoints only — no GGUF files):
```
outputs/{npc_key}/
  adapter_model.safetensors
  adapter_config.json
  chat_template.jinja
  tokenizer_config.json
  tokenizer.json
  README.md
  checkpoint-N/
  runs/{run_id}/
```

**Exports** (GGUF only — Unity-ready):
```
exports/{npc_key}/
  {npc_key}-{model_short}-{quant}.gguf   ← e.g. chemistry_instructor-llama3.2-3b-q4_k_m.gguf
  manifest.json                           ← auto-generated metadata for Unity
```

**Model Short Name Convention:**
| Model ID | Short Name |
|----------|-----------|
| `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` | `llama3.2-3b` |
| `unsloth/Qwen3-1.7B-bnb-4bit` | `qwen3-1.7b` |
| `unsloth/Llama-3.1-8B-Instruct-bnb-4bit` | `llama3.1-8b` |

Derivation: strip org, strip `-Instruct-bnb-4bit` / `-bnb-4bit`, lowercase.

**Manifest.json per export:**
```json
{
  "npc_key": "chemistry_instructor",
  "npc_name": "ChemistryInstructor",
  "model_id": "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
  "model_short": "llama3.2-3b",
  "quantization": "q4_k_m",
  "gguf": "chemistry_instructor-llama3.2-3b-q4_k_m.gguf",
  "system_prompt": "...",
  "trained_at": "2026-05-12T09:16:00",
  "run_id": "20260512_fast-3b_001",
  "eval_loss": 0.8711,
  "eval_perplexity": 2.39
}
```

**5.2 Update `scripts/export.py`**
- Reads `adapter_config.json` to extract npc_key + model_id
- Outputs to `exports/{npc_key}/{npc_key}-{model_short}-{quant}.gguf`
- Also saves merged model to `exports/{npc_key}/{npc_key}-{model_short}-merged/`
- Writes `manifest.json` in the export dir

**5.3 Update `scripts/export_adapter.py`**
- Read adapter dir name as npc_key
- Output LoRA GGUF to `exports/{npc_key}/{npc_key}-lora-{outtype}.gguf`

**5.4 Update `scripts/deploy_to_unity.py`**
- Scan `exports/` instead of `outputs/` for GGUF files
- Read `manifest.json` from each export dir instead of guessing metadata
- Keep StreamingAssets copy logic intact

---

### Slice 6: Professional Evaluation Pipeline [PENDING]

**6.1 Eval directory structure**
```
eval/
  training-metrics/
    chemistry_instructor.yaml        ← parsed TB metrics as structured data
    bible_instructor.yaml
  reports/
    chemistry_instructor/
      eval_2026-05-12.md             ← full side-by-side comparison report
      eval_2026-05-12.html           ← HTML report with embedded Matplotlib loss plots
  comparisons/
    chemistry_instructor_vs_baseline_2026-05-12.md
  results/
    eval_results.jsonl               ← tracked by track_eval_results.py
```

**6.2 TensorBoard integration**
- `evaluate.py --training-metrics outputs/{npc_key}/runs/` → saves parsed loss curves to `eval/training-metrics/{npc_key}.yaml`
- `evaluate.py --report-html` → generates HTML with embedded Matplotlib loss curves from TB data
- Report includes: loss curve, eval perplexity trend, constraint pass rates, quality score distribution

**6.3 Create `scripts/compare_runs.py`**
- Compare two or more runs for the same NPC
- Extract TensorBoard metrics from each run
- Produce markdown comparison report in `eval/comparisons/`
- Include: final eval loss, perplexity, training time, constraint pass rates
- Gracefully handle missing TensorBoard files

**6.4 Update `scripts/evaluate.py`**
- `--training-metrics` → parse TB, save structured metrics
- `--report-html` → generate HTML with Matplotlib loss plots
- Default `--output` → `eval/reports/{npc_key}/eval_{date}.md`
- `--track` → append results to `eval/results/eval_results.jsonl`

**6.5 Update `scripts/track_eval_results.py`**
- Default local path → `eval/results/eval_results.jsonl`
- `--show` → pretty-print from `eval/results/`

---

### Slice 7: Professional Frontend [PENDING]

Upgrade `scripts/dashboard.py` → `frontend/app.py` using lightweight approach:

**Tech stack:** HTMX + Alpine.js + Chart.js (no build toolchain needed)

**Features:**
- **Config Browser** — browse `configs/presets/`, view YAML contents, launch training
- **Run Explorer** — browse `outputs/{npc_key}/runs/`, view loss curves via Chart.js, compare runs
- **Live GPU/Memory** — WebSocket-based real-time metrics (already partially implemented)
- **Dataset Viewer** — browse `datasets/{npc_key}/{technique}/`, view samples
- **Export Manager** — view `exports/{npc_key}/`, trigger exports, view manifests
- **Eval Reports** — browse `eval/reports/` and `eval/comparisons/`
- **Training Launcher** — select NPC, preset, technique, and launch training with one click

**Architecture:**
- FastAPI backend with HTMX server-rendered partials
- Alpine.js for interactive UI components (tabs, modals, toggles)
- Chart.js for loss curves and metrics visualization
- WebSocket from `scripts/dashboard.py` reused for live metrics

---

### Slice 8: Subject Spec Schema Standardization [PENDING]

Update all `subjects/*.json` to match AGENTS.md documented fields:

Required sections: `identity`, `teaching`, `dialogue`, `quest`, `refusal`, `research_queries`

Migration:
- Add missing fields to existing specs
- Update `scripts/generate_dataset.py` to handle both old and new schema
- Validate all specs with a schema check

---

### Slice 9: Migration & Cleanup [PENDING]

**9.1 Move existing files**

| From | To | Action |
|------|----|--------|
| `datasets/chemistry_instructor.jsonl` | `datasets/chemistry_instructor/notebooklm/train.jsonl` | Move |
| `datasets/chemistry_instructor_validation.jsonl` | `datasets/chemistry_instructor/notebooklm/validation.jsonl` | Move |
| `datasets/chemistry_instructor_ollama.jsonl` | `datasets/chemistry_instructor/ollama/train.jsonl` | Move |
| `datasets/chemistry_instructor_ollama_validation.jsonl` | `datasets/chemistry_instructor/ollama/validation.jsonl` | Move |
| `datasets/bible_instructor.jsonl` | `datasets/bible_instructor/notebooklm/train.jsonl` | Move |
| `datasets/bible_instructor_validation.jsonl` | `datasets/bible_instructor/notebooklm/validation.jsonl` | Move |
| `datasets/marvel_instructor.jsonl` | `datasets/marvel_instructor/notebooklm/train.jsonl` | Move |
| `datasets/marvel_instructor_validation.jsonl` | `datasets/marvel_instructor/notebooklm/validation.jsonl` | Move |
| `datasets/world_map_guide.jsonl` | `datasets/world_map_guide/notebooklm/train.jsonl` | Move |
| `datasets/world_map_guide_validation.jsonl` | `datasets/world_map_guide/notebooklm/validation.jsonl` | Move |
| `outputs/chemistry_instructor/chemistry_instructor-lora.f16.gguf` | `exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-f16.gguf` | Move |
| `outputs/default/default-lora.f16.gguf` | `exports/default/default-llama3.2-3b-f16.gguf` | Move |
| `outputs/default/default-lora.q8_0.gguf` | `exports/default/default-llama3.2-3b-q8_0.gguf` | Move |
| `outputs/from_colab_training/chemistry_instructor/` | `outputs/colab/chemistry_instructor/` | Move + flatten |

**9.2 Regenerate q4_k_m exports**
For each trained model:
```bash
python scripts/export.py outputs/{npc_key}/ --quantization q4_k_m
```
This produces `exports/{npc_key}/{npc_key}-llama3.2-3b-q4_k_m.gguf`

**9.3 Run first baseline evaluation**
For each NPC:
```bash
python scripts/evaluate.py \
  --candidate exports/{npc_key}/*.gguf \
  --val-data datasets/{npc_key}/notebooklm/validation.jsonl \
  --output eval/reports/{npc_key}/eval_2026-05-12.md \
  --report-html \
  --track
```

**9.4 Initialize git**
- Create `.gitignore` excluding: `outputs/`, `datasets/`, `exports/`, `eval/`, `unsloth_env/`, `__pycache__/`, `*.pyc`
- `git init` + initial commit

---

## Sequencing

| Slice | Name | Dependencies | Can run in parallel with |
|-------|------|-------------|--------------------------|
| 1 | Workflow docs | None | All others |
| 2 | Config & presets | None | 1, 3, 8 |
| 3 | Dataset restructure | None | 1, 2, 8 |
| 4 | Run IDs | Slice 2 | 1, 3, 8 |
| 5 | Export/eval restructure | Slice 4 (partially) | 1, 6, 7 |
| 6 | Eval pipeline | Slice 5 | 1, 7, 8 |
| 7 | Frontend | Slice 5 (for data display) | 1, 6, 8 |
| 8 | Subject schema | None | 1, 2, 3 |
| 9 | Migration & cleanup | Slices 2, 3, 5 | None (must be last) |

**Recommended execution order:**
Phase A (parallel): Slices 1, 2, 3, 8
Phase B: Slices 4, 5
Phase C: Slices 6, 7 (parallel)
Phase D: Slice 9 (final)

---

## Acceptance Criteria

- [ ] All 5 workflow docs written in OLLAMA_WORKFLOW.md style, linked from README
- [ ] PRESETS dict removed from train.py; presets load from `configs/presets/*.yaml`
- [ ] `output_dir` stripped from all YAML config defaults (set to `outputs/default`)
- [ ] Datasets organized as `datasets/{npc_key}/{technique}/train.jsonl` and `validation.jsonl`
- [ ] Training produces `outputs/{npc_key}/runs/{run_id}/` with frozen config + metrics + `latest` symlink
- [ ] Exports go to `exports/{npc_key}/{npc_key}-{model_short}-{quant}.gguf` with manifest.json
- [ ] `scripts/compare_runs.py` produces valid comparisons in `eval/comparisons/`
- [ ] `evaluate.py --report-html` produces HTML with Matplotlib loss plots
- [ ] Frontend dashboard shows configs, runs, live metrics, export manager
- [ ] All `subjects/*.json` pass schema validation (identity, teaching, dialogue, quest, refusal, research_queries)
- [ ] All existing datasets migrated to technique subdirectories
- [ ] All existing GGUF files moved from outputs/ to exports/ with correct naming
- [ ] q4_k_m exports generated for all trained models
- [ ] `deploy_to_unity.py` scans `exports/` not `outputs/`
- [ ] `python scripts/train.py subjects/chemistry_instructor.json --from-spec --preset fast-3b` works end-to-end
- [ ] Git repo initialized with proper `.gitignore`
- [ ] All existing trained adapters remain loadable

---

## Required Evidence

| Requirement | Evidence to inspect | Where evidence is recorded |
|-------------|---------------------|---------------------------|
| Workflow docs | All 5 docs exist in `docs/` | `progress.jsonl` |
| YAML presets | `configs/presets/` + no PRESETS dict in train.py | `progress.jsonl` |
| Dataset structure | `datasets/{npc_key}/{technique}/train.jsonl` exists | `progress.jsonl` |
| Run ID training | `outputs/{npc_key}/runs/{run_id}/config.yaml` exists | `progress.jsonl` |
| Export structure | `exports/{npc_key}/manifest.json` exists | `progress.jsonl` |
| Eval reports | `eval/reports/{npc_key}/eval_*.md` exists | `progress.jsonl` |
| Frontend | Frontend launches, shows data | `progress.jsonl` |
| Migration | All files moved per migration table | `progress.jsonl` |
| q4_k_m quant | `exports/{npc_key}/*-q4_k_m.gguf` exists | `progress.jsonl` |
| End-to-end test | Train + export + eval works for any NPC | `progress.jsonl` |
| Backward compat | Existing adapters loadable | `progress.jsonl` |

---

## Completion Audit

Before marking the goal complete:
1. Map every acceptance criterion to concrete evidence in `progress.jsonl`
2. Verify the end-to-end flow: `generate_dataset → train → export → eval` works
3. Confirm all existing trained adapters and GGUF exports remain loadable
4. Verify no regressions in `scripts/train.py --from-spec`
5. Check that all existing files were migrated (no orphaned datasets or GGUF in outputs/)
