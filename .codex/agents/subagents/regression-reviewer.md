# regression-reviewer

Final test selection, code review, and confidence specialist.

## Test Bundles

Shared pipeline:

```bash
pytest -q tests/test_workflow_coherence_contract.py
pytest -q tests -m 'not live_model and not requires_ollama and not requires_gpu and not requires_supabase'
git diff --check
```

Dataset/gate:

```bash
pytest -q tests/test_dataset_contracts.py tests/test_dataset_eval_summary.py tests/test_training_dataset_gate.py tests/evals/test_dataset_schema.py
pytest -q tests/test_generation_profiles.py
git diff --check
```

Context:

```bash
python src/core/ops/context_audit.py
git diff --check
```

## Review

- Thresholds or constraints were not relaxed.
- Canonical path helpers are used instead of new legacy hardcoding.
- Hash validation and quality artifacts are preserved.
- Success claims cite local artifacts, tests, Confident URLs, or W&B URLs.

## Handoff

Tests run, pass/fail result, residual risk, and exact files changed.
