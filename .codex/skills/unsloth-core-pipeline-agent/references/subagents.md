# Pipeline Subagents

Use these as role contracts when delegating pipeline work. Each subagent should
read `AGENTS.md`, `.codex/references/project-context.md`, and only the specific
files needed for its stage. All subagents must avoid stale `.hermes`, `.agents`,
`.opencode`, `.gemini`, and `.pi` instructions unless explicitly asked to compare
or migrate them.

Concrete prompt files are stored under `.codex/agents/`:

- Main agent: `.codex/agents/ucore-pipeline-chief.agent.md`
- Subagents: `.codex/agents/subagents/*.md`

## Orchestrator: ucore-pipeline-chief

Owns source-of-truth selection, pipeline routing, anti-loop decisions, and final
acceptance. It does not blindly rerun stages; it inspects artifacts first.

Inputs:
- NPC key, target stage, production vs smoke intent.
- Latest `./ucore strategy --profile npc-production-grounded` output.
- Latest pipeline artifacts and known blockers.

Must check:
- Active NPC is `history_guide` or `chef_assistant`.
- Production technique is `ollama`, not template.
- `quality_failures.json` is preserved as repair input.
- Base+LoRA eval is used for adapter GGUFs.

Outputs:
- Stage owner selected.
- Exact commands to run.
- Handoff artifact list.
- Final `Done/Changed/Ran/Result/Blocked/Next`.

## Subagent: context-sentinel

Read-only context hygiene and drift auditor.

Owns:
- Detecting stale NotebookLM/template/subjects-path claims.
- Comparing live tool output with `AGENTS.md`, `.codex/references/*`, and docs.
- Flagging inactive NPC leakage.

Key files:
- `AGENTS.md`
- `.codex/references/project-context.md`
- `.codex/references/current-commands.md`
- `docs/project-state.md`
- `docs/training-workflow.md`
- `docs/reports/pipeline_visualgraph.html`

Must run when context changed:
```bash
python src/core/ops/context_audit.py
./ucore strategy --profile npc-production-grounded
```

Do not:
- Update global memory unless the user explicitly asks.
- Treat `.hermes` or `.opencode` as canonical.

## Subagent: spec-grounding-curator

Owns reference docs, NPC specs, generation readiness, and grounding coverage.

Key files:
- `data/npcs/specs/<npc>.json`
- `data/npcs/reference_docs/<npc>_primer.md`
- `src/core/dataset/validate_subject_spec.py`
- `src/config/workflow_context.py`

Must run:
```bash
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
```

Review for:
- Missing or weak reference doc contract.
- Concepts not supported by primer text.
- Dialogue limits and metadata requirements.
- Production readiness for active NPCs only.

Handoff:
- Validated spec path.
- Primer gaps or proposed narrow edits.
- Generation-ready status and warnings.

## Subagent: dataset-generation-engineer

Owns grounded `ollama` generation, generator prompts, category distribution, and
top-up/repair generation.

Key files:
- `src/core/dataset/generate_dataset.py`
- `src/core/dataset/generate_dataset_ollama.py`
- `src/core/dataset/generation_profiles.py`
- `src/core/dataset/dataset_contracts.py`
- `data/datasets/<npc>/ollama/train.jsonl`
- `data/datasets/<npc>/ollama/train_manifest.json`

Must prefer:
```bash
./ucore generate data/npcs/specs/<npc>.json --technique ollama
```

Review for:
- Underfilled categories before sanitize.
- Guardrail rejections and `generation_errors.json`.
- Generic, terse, ungrounded, or off-role rows.
- Checkpoint reuse when `--fresh` is needed.

Do not:
- Use template for production.
- Delete weak rows to hide failures.

Handoff:
- Raw `train.jsonl`.
- `validation.jsonl`.
- `train_manifest.json`.
- Generation errors and category counts.

## Subagent: sanitizer-gate-engineer

Owns sanitize, structural quality, DeepEval local/remote gate, Confident upload,
W&B dataset-quality tracking, and quality artifact interpretation.

Key files:
- `src/core/dataset/sanitize_dataset.py`
- `src/core/dataset/dataset_eval.py`
- `tests/evals/test_dataset_generation_quality.py`
- `tests/evals/metrics.py`
- `data/datasets/<npc>/ollama/train_clean.jsonl`
- `quality_summary.json`
- `quality_failures.json`
- `quality_report.json`
- `confident_insights.json`

Must run:
```bash
./ucore sanitize data/datasets/<npc>/ollama/train.jsonl \
  --output data/datasets/<npc>/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json --technique ollama --mode fast --judge-model qwen2.5:7b
```

For production release checks, use strategy profile values:
- mode: `release`
- judge provider: `wandb`
- Confident: required when profile says so
- W&B: enabled when profile says so

Review for:
- `status != ok`.
- Distribution gaps.
- Unknown rows.
- Sanitizer quality issues.
- Hash mismatch between `train_clean.jsonl` and `quality_summary.json`.
- Null-heavy or inconclusive judge output.

Handoff:
- Fresh passing `quality_summary.json`.
- Failure classes from `quality_failures.json`.
- Confident URL or explicit reason none exists.
- W&B run URL or explicit reason none exists.

## Subagent: training-vram-engineer

Owns low-VRAM preflight, training preset selection, dataset gate enforcement,
LoRA hyperparameters, and W&B training telemetry.

Key files:
- `src/core/training/train.py`
- `etc/npc-production-strategy.yaml`
- `etc/presets/*.yaml`
- `artifacts/models/<npc>/runs/<run_id>/`
- `artifacts/models/<npc>/best`
- `artifacts/models/<npc>/latest`

Must run before training:
```bash
./ucore audit check
nvidia-smi
ollama ps
```

Training command:
```bash
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json \
  --technique ollama --preset fast-3b --export-gguf
```

Review for:
- Dataset gate freshness via `dataset_quality_gate_errors()`.
- Ollama occupying VRAM.
- Preflight preset downgrade.
- CUDA OOM and Triton/GCC issues.
- Loss suspiciously high or low.
- Missing run pointers.

Do not:
- Use `--allow-ungated-dataset` for production.
- Treat `safe-any` fallback as a quality win without recording why.

Handoff:
- Run ID.
- Effective preset.
- Training metrics.
- W&B URL if present.
- Adapter checkpoint path.

## Subagent: gguf-unity-exporter

Owns adapter GGUF export, manifest checks, and LLMUnity copy readiness.

Key files:
- `src/core/export/export.py`
- `src/core/export/export_adapter.py`
- `src/core/export/deploy_to_unity.py`
- `artifacts/exports/<npc>/<npc>-lora-f16.gguf`
- `artifacts/exports/<npc>/manifest.json`
- Unity `Assets/StreamingAssets/Models/`

Must verify:
```bash
ls -lh artifacts/exports/<npc>/<npc>-lora-f16.gguf
```

Deploy command:
```bash
./ucore deploy --unity-project "/home/athar/Setup Guide In-Editor Tutorial"
```

Review for:
- Adapter mode vs full-merge mode.
- Correct base model provenance.
- Manifest `mode: adapter`.
- Checksums during Unity copy.
- NPC system prompt in deployment manifest.

Do not:
- Present adapter-only GGUF as standalone.
- Copy inactive NPCs unless user reactivates them.

Handoff:
- GGUF path and size.
- Export manifest.
- Unity deployment manifest path.
- Base model pairing requirement.

## Subagent: dashboard-unity-verifier

Owns dashboard command/report wiring and final Unity runtime readiness checks.
Use this after backend command changes, report-path changes, deployment changes,
or when the user wants the pipeline visible/operable from the dashboard.

Key files:
- `src/dashboard/unity-npc-llm-training-dashboard/`
- `src/core/ops/pipeline_db.py`
- `src/core/ops/artifact_registry.py`
- `artifacts/eval/reports/<npc>/`
- `artifacts/exports/<npc>/manifest.json`
- Unity `Assets/StreamingAssets/Models/`

Dashboard checks:
```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run build
```

Review for:
- Dashboard commands invoking `./ucore` with current canonical paths.
- `/api/jobs/state` reflecting active runs and errors.
- `/api/eval-reports` finding HTML/Markdown/index reports.
- GGUF export paths displayed as adapter files, not standalone models.
- Unity deployment manifest includes NPC key, LoRA path, system prompt, subject.
- Shared base model remains separate from LoRA adapters.

Do not:
- Treat dashboard UI success as proof that CLI artifacts passed gates.
- Deploy inactive NPCs unless user reactivates them.

Handoff:
- Build result.
- API/report paths checked.
- Unity manifest path and copied adapter list.
- Any dashboard/backend schema mismatch.

## Subagent: runtime-eval-feedback-engineer

Owns base+LoRA side-by-side evaluation, DeepEval model-quality options,
feedback JSON, weak concept slices, density repair, and anti-loop decisions.

Key files:
- `src/core/evaluation/evaluate.py`
- `src/core/training/feedback_loop.py`
- `src/core/ops/npc_production_strategy.py`
- `artifacts/eval/reports/<npc>/`
- `artifacts/eval/results/feedback/<npc>.json`

Runtime eval command:
```bash
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json \
  --report-html --feedback-json artifacts/eval/results/feedback/<npc>.json
```

Feedback command:
```bash
./ucore feedback artifacts/eval/results/feedback/<npc>.json \
  --json --strategy-profile npc-production-grounded
```

Review for:
- Candidate win rate below readiness threshold.
- Constraint violations: sentence count, name, AI disclaimer, think tags.
- Weak categories/concepts.
- `avg_candidate_words` vs baseline density.
- `strategy_decision` and `density_decision`.

Anti-loop:
- One exact Confident failure repair.
- One density repair.
- One training preset variant.
- Then escalate to shared strategy/preset.

Handoff:
- HTML/Markdown report paths.
- `.index.json` summary.
- Feedback JSON.
- Next bounded repair class.

## Subagent: regression-reviewer

Owns test selection, code review, and final confidence before declaring success.

Run based on touched surface:

```bash
pytest -q tests/test_workflow_coherence_contract.py
pytest -q tests/test_dataset_contracts.py tests/test_dataset_eval_summary.py tests/test_training_dataset_gate.py tests/evals/test_dataset_schema.py
pytest -q tests/test_generation_profiles.py
pytest -q tests -m 'not live_model and not requires_ollama and not requires_gpu and not requires_supabase'
git diff --check
```

Review for:
- Changed thresholds or relaxed constraints.
- New hardcoded legacy `subjects/` paths where path helpers should be used.
- Missing artifact hash validation.
- Claims not backed by local files, Confident URL, W&B URL, or test output.

Handoff:
- Tests run and result.
- Residual risks.
- Exact files changed.
