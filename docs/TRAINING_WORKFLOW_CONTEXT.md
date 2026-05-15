# Training Workflow Context

Purpose: compact, high-signal context for AI agents and humans working on the Unsloth_Core NPC LoRA training workflow. Prefer this as the orientation document before changing training, generation, export, dashboard, or Unity deployment code.

## Ground Rules

- Use `./ucore` as the public interface. Direct `python scripts/*.py` calls are implementation details unless debugging internals.
- Production NPC datasets should use `onyx` unless a subject has a dedicated technique such as `docs` for `workflow_assistant`.
- Use `onyx` when local source material is already indexed and you need retrieval-grounded, reproducible generation without NotebookLM rate limits.
- Template generation is only for smoke tests and scaffolding. Do not train production LoRAs on template data.
- Dataset paths are canonical: `datasets/{npc_key}/{technique}/train.jsonl` and `datasets/{npc_key}/{technique}/validation.jsonl`.
- Sanitized training data is written as `train_clean.jsonl`; `train.py` prefers it when present and falls back to `train.jsonl`.
- Outputs and deployable artifacts are separate: LoRA run outputs live in `outputs/{npc_key}/`; GGUF exports live in `exports/{npc_key}/`.
- Default deployable quantization is `q4_k_m`.

## End-to-End Flow

The standard pipeline is:

```bash
./ucore pipeline subjects/{npc_key}.json --preset fast-3b --technique onyx --wandb --track
```

Internally this runs:

1. Generate dataset:
   - Command: `./ucore generate subjects/{npc_key}.json --technique onyx`
   - Script: `scripts/generate_dataset.py`
   - Output: `datasets/{npc_key}/onyx/train.jsonl` plus `validation.jsonl` when enough examples exist.
2. Sanitize dataset:
   - Command: `./ucore sanitize datasets/{npc_key}/{technique}/train.jsonl --output datasets/{npc_key}/{technique}/train_clean.jsonl --strict-canonical`
   - Script: `scripts/sanitize_dataset.py`
   - Output: cleaned ChatML JSONL.
3. Train LoRA:
   - Command: `./ucore train subjects/{npc_key}.json --preset fast-3b --technique {technique} --export-gguf`
   - Script: `scripts/train.py`
   - Output: `outputs/{npc_key}/runs/{run_id}/` and `outputs/{npc_key}/latest` symlink.
4. Export GGUF:
   - Usually triggered by `--export-gguf` in training or pipeline.
   - Standalone command: `./ucore export {npc_key} --quantization q4_k_m`.
   - Output: `exports/{npc_key}/{npc_key}-{model_short}-q4_k_m.gguf` and `exports/{npc_key}/manifest.json`.
5. Smoke test:
   - Command: `./ucore smoke exports/{npc_key}/{file}.gguf --spec subjects/{npc_key}.json --track`
   - Script: `scripts/smoke_test.py`.

## Preflight Checklist Before Expensive Training

Run these before launching non-smoke jobs:

```bash
./ucore validate-spec subjects/{npc_key}.json --strict
./ucore validate-config --spec subjects/{npc_key}.json --preset fast-3b --data datasets/{npc_key}/{technique}/train.jsonl --require-canonical --strict
./ucore plan-execution --spec subjects/{npc_key}.json --preset fast-3b
```

Use `./ucore plan-execution --json` for automation. Placement uses `configs/workload-policy.yaml` and considers estimated training VRAM, NotebookLM dataset size, and local caps.

## Config Resolution

Training config precedence is:

```text
subject spec or base YAML
  < configs/presets/{preset}.yaml
  < CLI overrides
```

Important fields:

- Base model: `model`, `model_id`, `llm.model_name`, or `llm.base_model`; default is `unsloth/Llama-3.2-3B-Instruct-bnb-4bit`.
- Dataset technique: `technique` or `dataset.technique`; default is `onyx`.
- Training data: `datasets/{npc_key}/{technique}/train_clean.jsonl` if present, otherwise `train.jsonl`.
- Output dir: `outputs/{npc_key}/` with run-specific subdirs.
- Logging: TensorBoard enabled by default; W&B enabled by `--wandb` or `configs/presets/wandb.yaml`.

Common presets:

- `smoke`: quick 10-step validation, not production.
- `fast-3b`: standard 3B local training preset.
- `safe-any`: fallback for CUDA OOM or constrained VRAM.
- `wandb`: enables W&B but is single-select; use `--wandb` with another preset for normal training.

## Dataset Contract

Each JSONL row should be ChatML-style:

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}],"metadata":{"npc_key":"...","category":"...","source":"onyx"}}
```

Training converts `messages` to model text through the tokenizer chat template when available. Rows with an explicit non-empty `text` field are also accepted. Invalid JSON lines are skipped during training, but sanitization should catch shape problems earlier.

Technique priority in shared path helpers is: `docs`, `onyx`, `ollama`, `openai`, `anthropic`, `template`.

## Onyx Local Retrieval Notes

Onyx generation writes canonical ChatML under `datasets/{npc_key}/onyx/`. It is retrieval-only by default to protect local CPU/GPU resources: bounded top-k, bounded context chars, and per-run search caching. Add `--onyx-use-llm` only when the local Ollama model can rewrite retrieved chunks without competing with training.

Useful command:

```bash
./ucore generate subjects/{npc_key}.json --technique onyx --onyx-max-results 3 --onyx-max-context-chars 1200
```

See `docs/ONYX_WORKFLOW.md` for auth, resource policy, and troubleshooting.

## Onyx Production Notes

Onyx is the default production dataset source because it is retrieval-grounded from locally indexed material — no rate limits, no external API calls. Onyx generation is resource-conscious by default (bounded top-k, bounded context chars, per-run search caching). For production work, ensure your source documents are well-indexed in Onyx before generating.

Use `--onyx-use-llm` only when the local Ollama model can run comfortably while Onyx is already indexed.

```bash
./ucore generate subjects/{npc_key}.json --technique onyx --onyx-max-results 3 --onyx-max-context-chars 1200
```

## Training Internals

`scripts/train.py` loads the base model with Unsloth `FastLanguageModel.from_pretrained(load_in_4bit=True)`, attaches LoRA target modules (`q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj`), and trains with TRL `SFTTrainer`.

Defaults and behaviors to remember:

- `train_on_responses_only` defaults on, but the trainer API must support it; otherwise a warning is printed and training continues.
- `packing` is usually enabled.
- Optimizer is `adamw_8bit`.
- Seed and data seed are fixed at `42`.
- Eval split support is currently not wired in `train.py`; validation files exist for other checks/evaluation but `eval_dataset` is set to `None` in the current training loop.
- `latest` symlink always points to the newest run; `best` updates only when promotion rules pass.
- Promotion thresholds are read from `configs/promotion-rules.yaml` when present.

Run layout:

```text
outputs/{npc_key}/
  latest -> runs/{run_id}
  best -> runs/{run_id}       # only if promotion rules pass
  runs/{run_id}/
    adapter_model.safetensors
    adapter_config.json
    tokenizer.json
    tokenizer_config.json
    config_snapshot.yaml
    training_metrics.json
    runs/events.out.tfevents.*
```

## W&B and TensorBoard

Use W&B for serious runs:

```bash
./ucore train subjects/{npc_key}.json --preset fast-3b --wandb --export-gguf
```

W&B config defaults are in `configs/lora-sft-base.yaml` and `configs/presets/wandb.yaml`. Current project convention is entity `andreabenathar-twl-games`, project `unsloth-core`. TensorBoard logs are written under the run output directory unless disabled with `--no-tensorboard`.

## Export and Unity Deployment

Full GGUF export:

```bash
./ucore export {npc_key} --quantization q4_k_m
```

LoRA-only adapter export for LLMUnity side-loading:

```bash
./ucore export-adapter outputs/{npc_key}/latest --outtype f16
```

Deploy to Unity:

```bash
./ucore deploy --dry-run
./ucore deploy
```

Deployment copies GGUF files into the Unity project's `Assets/StreamingAssets/Models/` directory and writes a manifest consumed by the Unity import path.

## Debugging Playbook

- Dataset missing: check `datasets/{npc_key}/{technique}/train_clean.jsonl` first, then `train.jsonl`; verify technique matches spec and CLI.
- Wrong technique: pass `--technique` explicitly to both `generate` and `train`.
- CUDA OOM: retry with `--preset safe-any`, lower `--max-seq-len`, or move to Colab via planning.
- Loss is flat/high: validate ChatML shape, confirm response-only masking warning did not appear, and inspect whether dataset is template/smoke quality.
- Export missing: inspect `outputs/{npc_key}/latest`, then run `./ucore export {npc_key}`; use `./ucore export-resume` for interrupted exports.
- Dashboard mismatch: compare frontend command payloads with `./ucore --help` and the `ucore` parser; stale UI values often come from frontend/control-plane contract drift.

## Source Map

- Unified CLI: `ucore`
- Dataset generation: `scripts/generate_dataset.py`
- Sanitization: `scripts/sanitize_dataset.py`
- Training: `scripts/train.py`
- Local/Colab placement: `scripts/plan_execution.py`, `scripts/plan_batch_execution.py`, `configs/workload-policy.yaml`
- Presets: `configs/presets/*.yaml`
- Base training config: `configs/lora-sft-base.yaml`
- Shared paths and naming: `_config/paths.py`
- Export: `scripts/export.py`, `scripts/export_adapter.py`, `scripts/export_resume.py`
- Smoke/eval: `scripts/smoke_test.py`, `scripts/evaluate.py`, `scripts/compare_runs.py`
- Dashboard: `frontend_control/unity-npc-llm-training-dashboard/`
- Related docs: `docs/TRAINING_WORKFLOW.md`, `docs/ONYX_WORKFLOW.md`, `docs/DATASET_CONTRACT_WORKFLOW.md`, `docs/EXPORT_WORKFLOW.md`, `docs/reference/CLI_REFERENCE.md`
