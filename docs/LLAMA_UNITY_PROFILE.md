# Llama-Only Profile for Unity Dialogue NPCs

This project now supports a clean Llama-first profile for Unity LLM dialogue deployment.

## Decisions made

1) Keep backward compatibility, but make Llama the default strategy
- Existing presets remain to avoid breaking old workflows.
- New recommended presets are explicitly Llama-focused.

2) Introduce explicit Llama presets
- `llama-1b-fast` — fastest iteration loop
- `llama-3b-fast` — default balance for quality/speed
- `llama-3b-quality` — longer training for better responses

3) Add validation guardrails
- Config validation warns when model is non-Llama.
- Use strict mode to fail preflight when warnings exist.

## Recommended baseline commands

Validate config first:

```bash
./ucore validate-config \
  --spec subjects/chemistry_instructor.json \
  --preset llama-3b-fast \
  --data datasets/chemistry_instructor/notebooklm/train.jsonl \
  --strict
```

Train:

```bash
./ucore train subjects/chemistry_instructor.json --from-spec --preset llama-3b-fast
```

Higher quality run:

```bash
./ucore train subjects/chemistry_instructor.json --from-spec --preset llama-3b-quality
```

## Clean-architecture intent

- Base config is generic.
- Presets encode model/workload intent.
- Validation enforces path + model conventions before expensive training.
- Run manifests in `outputs/{npc_key}/runs/{run_id}/run_manifest.json` provide reproducibility.
