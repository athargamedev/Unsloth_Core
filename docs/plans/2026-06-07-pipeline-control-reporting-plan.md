# Pipeline Control and Reporting Plan

Date: 2026-06-07

## Diagnosis

The NPC pipeline has strong tools, but the operator experience is still too
script-shaped. Generation, sanitization, dataset evaluation, training, export,
runtime evaluation, Confident/W&B publishing, Modal remote execution, feedback
classification, and promotion each own separate flags and artifacts. That makes
it easy to run a valid command sequence that is not a coherent experiment.

The fix is not another command list. The fix is a single controlled pipeline
contract that resolves every flag before execution, records every decision, and
produces one report bundle that says what to improve before the next NPC run.

## Current Control Surfaces

- `etc/npc-production-strategy.yaml` owns production defaults: technique,
  density, quality gate, training, runtime eval, and anti-loop limits.
- `src/core/orchestration/workflow_spec.py` emits canonical stage commands, but
  still hardcodes defaults instead of resolving the whole strategy profile.
- `src/core/orchestration/target_runner.py` already knows target plans, cached
  stages, artifact lineage, run registry, and GPU leases.
- `src/core/dataset/dataset_eval.py` writes `quality_summary.json`,
  `quality_failures.json`, `quality_report.json`, and Confident insights.
- `src/core/evaluation/evaluate.py` and `compare_runs.py` generate final runtime
  comparison reports, but are not yet mandatory outputs of a production target.
- `src/core/training/feedback_loop.py` can classify bounded repair decisions,
  but the output is not promoted to a first-class operator report.
- `tests/test_cli_schema_drift.py` already detects CLI/schema drift, which
  should become a report input instead of a passive test artifact.
- `docs/reports/2026-06-07-integration-readiness-report.md` captures the
  current Confident AI, W&B, DeepEval, and Modal readiness state. Modal is
  installed as a Python client but has no project execution lane yet.

## Target State

One command should be enough for a dry-run or execution:

```bash
./ucore target run \
  --npc-key chef_assistant \
  --profile npc-production-grounded \
  --target-stage evaluate \
  --report-bundle
```

That command should resolve a `PipelineRunSpec` before any stage starts. The run
spec must include every effective flag:

- NPC key, spec path, reference doc path, technique, and active/inactive status.
- Generation model, temperature, retry policy, batch size, multi-turn ratio,
  grounding mode, and freshness policy.
- Sanitizer strictness, metadata repair policy, and output paths.
- Dataset-eval judge provider/model, mode, cases per category, Confident/W&B
  settings, cache policy, and soft/hard gate behavior.
- Training model, preset, max sequence length, LoRA rank/alpha, batch,
  gradient accumulation, packing, response masking, export settings, and GPU
  lease policy.
- Runtime-eval baseline, candidate adapter, base model, judge provider/model,
  report formats, feedback JSON path, and promotion threshold.
- Integration settings and evidence for DeepEval, Confident AI, W&B, and Modal:
  enabled flags, credential presence/scope, run IDs, URLs, artifact IDs, remote
  execution status, and unavailable reasons.

The resolved run spec should be written to:

```text
artifacts/reports/<npc_key>/<run_id>/pipeline_run_spec.json
```

## Report Bundle

Each production run should produce:

```text
artifacts/reports/<npc_key>/<run_id>/
  index.html
  summary.md
  pipeline_run_spec.json
  stage_status.json
  source_contract.json
  dataset_quality.json
  density_report.json
  grounding_report.json
  training_report.json
  runtime_eval_report.json
  feedback_decision.json
  integration_health.json
  modal_remote_run.json
  next_actions.json
```

The `summary.md` should answer, in order:

1. Is the NPC source package generation-ready?
2. Did the dataset meet category, density, formatting, grounding, and safety
   contracts?
3. Did training run with the intended profile and response-only masking?
4. Did runtime evaluation beat the baseline?
5. What exact source/spec/reference/prompt changes should happen next?
6. Are we allowed to run another per-NPC repair, or must we escalate to shared
   strategy?
7. Are Confident AI, W&B, DeepEval, and Modal configured, executed, and linked
   well enough to trust the result?

## Implementation Phases

### Phase 1: Resolve Flags Once

- Add `src/core/orchestration/run_spec.py`.
- Load `etc/npc-production-strategy.yaml`, spec JSON, reference doc metadata,
  model presets, CLI overrides, and hardware policy.
- Emit one typed `PipelineRunSpec`.
- Make `workflow_spec.build_stage_command()` consume `PipelineRunSpec` instead
  of hardcoded constants.
- Tests: strategy overrides, CLI overrides, active/inactive NPC handling,
  Confident/W&B/DeepEval/Modal flag propagation, and no legacy
  `generate --technique ollama` path in production.

### Phase 1B: Integration Audit

- Add `src/core/ops/integration_audit.py`.
- Add `./ucore audit integrations --profile npc-production-grounded --json`.
- Check DeepEval CLI/library, Confident AI key presence and project scope, W&B
  login/key state, Modal token/profile state, and interpreter coherence.
- Reports must record only secret presence/scope, never raw secret values.
- Production profiles must fail preflight when required integrations are absent
  unless the run spec explicitly marks them unavailable with a reason.

### Phase 2: Stage Reports Become Inputs

- Normalize stage outputs into machine-readable JSON fragments.
- Dataset stage reports include distribution, density, rejected rows, fallback
  counts, grounding failures, and prompt/guardrail rejection classes.
- Training stage report includes run id, loss, eval loss if available,
  response-only masking confirmation, GPU lease, OOM status, and export paths.
- Runtime eval report includes baseline/candidate win rate, category wins,
  sentence/word/format compliance, weak concepts, and feedback JSON.
- Integration report includes DeepEval run IDs/paths, Confident test run IDs and
  URLs, W&B run/artifact IDs and URLs, and Modal remote run IDs/artifact sync
  status.
- Tests: missing report fragments block promotion but do not delete artifacts.

### Phase 3: Bundle Builder

- Add `src/core/reports/pipeline_bundle.py`.
- Input: `PipelineRunSpec`, artifact registry, run registry, dataset quality
  outputs, training manifest, eval report index, Confident/W&B links, feedback
  JSON.
- Output: report directory with `summary.md`, `index.html`, and JSON fragments.
- Add `./ucore report bundle --npc-key ... --run-id ...` and wire
  `./ucore target run --report-bundle`.
- Tests: bundle renders when some optional cloud integrations are missing.

### Phase 3B: Modal Remote Lane

- Add `src/core/remote/modal_pipeline.py`.
- Add `./ucore modal plan` and `./ucore modal run`.
- Supported remote stages: `dataset-eval`, `train`, `evaluate`, and
  `report-bundle`.
- Modal outputs must sync back into `artifacts/reports/<npc_key>/<run_id>/`.
- Tests must mock Modal client calls and verify that run spec flags, secrets,
  stage inputs, and artifact sync contracts are honored.

### Phase 4: Improvement Engine

- Add a deterministic `next_actions.json` schema.
- Map quality failures to actions:
  - source contract gaps -> edit spec/reference doc
  - generation fallback spikes -> adjust prompt or guardrail contract
  - density gaps -> one bounded density repair
  - grounding false positives -> judge rubric/prompt update
  - weak runtime concepts -> targeted dataset supplement
  - training underfit/overfit -> bounded preset variant
- Use `classify_feedback_cycle()` to enforce anti-loop limits.
- Tests: after one exact repair, one density repair, and one training variant,
  the report recommends `escalate_shared_strategy`.

### Phase 5: Operator Dashboard

- Surface the same report bundle in the dashboard instead of reconstructing
  status from scattered artifacts.
- Add a run picker per NPC with active/inactive labeling.
- Show effective flags, stage cache state, next action, and links to Confident,
  W&B, Markdown, and HTML reports.

## Immediate Next Build Order

1. Implement `PipelineRunSpec` and refactor `workflow_spec.py`.
2. Implement `./ucore audit integrations` for DeepEval, Confident AI, W&B, and
   Modal.
3. Add `./ucore target plan --json` output that includes all effective flags.
4. Add report fragments for generation fallback and guardrail rejection counts.
5. Add `pipeline_bundle.py` and `./ucore report bundle`.
6. Add Modal remote stage planning/execution with artifact sync.
7. Make `target run --report-bundle` mandatory for production profiles.
8. Gate promotion on bundle presence, integration health, and runtime-eval
   readiness.

## Non-Negotiables

- Production generation uses `./ucore generate-ollama`, never the legacy shared
  generator path.
- Specs and reference docs must pass `--generation-ready` before generation.
- Generated datasets are evidence, but source contracts remain the primary fix
  surface.
- Do not lower thresholds to pass gates.
- Every repair loop must end in a report-backed decision, not another ad hoc
  command.
- Confident AI, W&B, DeepEval, and Modal evidence must be report fields, not
  console output.
