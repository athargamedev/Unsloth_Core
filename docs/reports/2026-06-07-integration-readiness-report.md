# Integration Readiness Report

Date: 2026-06-07

## Verdict

The integration stack is partially installed but not production-controlled yet.
DeepEval is usable from the project venv and has recent local run artifacts.
Confident AI, W&B, and Modal are not yet perfect because their credentials,
runtime checks, and report links are not resolved through one pipeline run spec.
Modal is the largest gap: the package is installed, but the repo has no actual
Modal execution path for generation, training, evaluation, or report bundling.

## Checked State

| Integration | Installed | Credentials in active shell | Repo integration | Report evidence |
|---|---:|---:|---|---|
| DeepEval | yes, `4.0.5` in `unsloth_env` | not required for local runs | dataset gate, runtime eval, tracing helpers | `.deepeval/`, `artifacts/eval/deepeval_runs/`, dataset quality JSON |
| Confident AI | via DeepEval | no exported `CONFIDENT_API_KEY` in current shell | dataset eval, remote eval, goldens, classifiers, tracing | `confident_insights.json`, optional Confident URLs when runs upload |
| W&B | yes, `0.26.1` in `unsloth_env` | no exported `WANDB_API_KEY` in current shell | training, dataset-eval judge provider, runtime eval tracking | not guaranteed unless run spec captures W&B URL/artifact IDs |
| Modal | yes, Python client `1.4.3` imports | no exported Modal token variables | not integrated yet; only UI dialog "modal" references exist | none |

## Current Artifacts Found

- `.deepeval/.latest_run_full.json`
- `.deepeval/.latest_test_run.json`
- `artifacts/eval/deepeval_runs/test_run_20260607_112438.json`
- `artifacts/eval/deepeval_runs/test_run_20260607_112739.json`
- `data/datasets/chef_assistant/ollama/quality_summary.json`
- `data/datasets/chef_assistant/ollama/quality_report.json`
- `data/datasets/chef_assistant/ollama/confident_insights.json`
- `data/datasets/history_guide/ollama/quality_summary.json`
- `data/datasets/history_guide/ollama/quality_report.json`
- `data/datasets/history_guide/ollama/confident_insights.json`

## Blocking Gaps

1. `PipelineRunSpec` does not yet resolve all integration flags and secrets.
2. `target run` does not require or emit a report bundle.
3. Confident AI keys may exist in local files, but the active process does not
   load/export them consistently. The report bundle must record only presence,
   project/organization scope, test run IDs, and URLs, never raw secrets.
4. W&B is installed, but login/key state is not enforced before production runs.
   Run URLs and artifact IDs are optional console output today, not guaranteed
   report fields.
5. DeepEval local artifacts exist, but their raw run JSON is not normalized into
   a stable pipeline report schema.
6. Modal is not wired. There is no `modal` profile, app file, remote execution
   command, artifact sync contract, or test.
7. The bare shell still has a Python shim mismatch: `.python-version` requests
   Python 3.12, while the reliable path is `unsloth_env/bin/python`. Pipeline
   commands must pin the interpreter instead of depending on pyenv shims.

## Required Report Bundle Fields

Every production run report must include:

- `deepeval.local_run_id`
- `deepeval.latest_run_path`
- `deepeval.metric_summary`
- `confident.enabled`
- `confident.key_scope`
- `confident.test_run_id`
- `confident.url`
- `confident.knowledge_retention_test_run_id`
- `wandb.enabled`
- `wandb.project`
- `wandb.entity`
- `wandb.run_id`
- `wandb.url`
- `wandb.artifact_names`
- `modal.enabled`
- `modal.app_name`
- `modal.function_name`
- `modal.run_id`
- `modal.artifact_sync_status`
- `integration_health.ok`
- `integration_health.blockers`

## Implementation Gates

### Gate 1: Credential and Runtime Preflight

Add `./ucore audit integrations --profile npc-production-grounded --json`.
It must check DeepEval CLI/library, Confident key presence and project scope,
W&B login/key state, Modal token/profile state, and pyenv/venv interpreter
coherence. It should return non-zero for production profiles when required
integrations are missing.

### Gate 2: PipelineRunSpec Integration Resolution

`PipelineRunSpec` must resolve every integration setting before execution:
judge provider, remote eval provider, Confident collections, W&B project/entity,
W&B inference project/entity, Modal profile/app/function, report bundle path,
and secret-presence booleans.

### Gate 3: Stage Output Normalization

Dataset eval, training, runtime eval, Confident, W&B, and Modal stages must each
write a JSON fragment under the run report directory. Console-only URLs are not
acceptable for production.

### Gate 4: Modal Remote Lane

Add an explicit Modal lane rather than treating remote work as ad hoc Colab:

- `src/core/remote/modal_pipeline.py`
- `./ucore modal plan`
- `./ucore modal run --stage dataset-eval|train|evaluate`
- artifact sync back into `artifacts/reports/<npc>/<run_id>/`
- tests that mock Modal client calls and verify flags/artifact contracts

### Gate 5: Report Bundle

`./ucore report bundle --npc-key ... --run-id ...` must merge local artifacts,
DeepEval, Confident, W&B, Modal, feedback decisions, and next actions into
`summary.md`, `index.html`, and machine-readable JSON.

## Immediate Build Order

1. Add `src/core/ops/integration_audit.py` and `./ucore audit integrations`.
2. Add tests for DeepEval/Confident/W&B/Modal readiness states.
3. Implement `PipelineRunSpec` with integration fields.
4. Refactor `workflow_spec.py` and `target_runner.py` to consume the run spec.
5. Add `src/core/reports/pipeline_bundle.py`.
6. Add Modal remote lane and artifact sync.
7. Make production `target run` fail if the integration audit or report bundle
   contract fails.

## Non-Negotiables

- Do not expose raw API keys in reports.
- Do not accept console-only integration evidence.
- Do not allow production promotion without report bundle links or explicit
  unavailable reasons for Confident, W&B, DeepEval, and Modal.
- Do not add more free-floating CLI recipes; all flags must resolve through the
  run spec.
