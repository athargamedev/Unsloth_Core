# Unsloth_Core Commands

## First Checks

```bash
git status --short
./ucore audit check
./ucore strategy --profile npc-production-grounded
./ucore validate-spec data/npcs/specs/history_guide.json --generation-ready
./ucore validate-spec data/npcs/specs/chef_assistant.json --generation-ready
```

## Production Pipeline Shape

```bash
./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --fresh
./ucore sanitize data/datasets/<npc>/ollama/train.jsonl \
  --output data/datasets/<npc>/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval data/npcs/specs/<npc>.json \
  --technique ollama --mode fast --judge-model qwen2.5:7b
PATH=/usr/bin:/bin:$PATH ./ucore train data/npcs/specs/<npc>.json \
  --technique ollama --preset fast-3b --export-gguf
./ucore evaluate --baseline <baseline> --candidate <candidate> \
  --base-model <base-gguf> --spec data/npcs/specs/<npc>.json --report-html
```

## Smoke/Dev Only

```bash
./ucore generate data/npcs/specs/<npc>.json --technique template
```

Template datasets are smoke/dev only. Never promote as production training data.

## Low-VRAM Preflight

```bash
nvidia-smi
ollama ps
./ucore audit check
```

If Ollama holds VRAM before train/eval, unload/stop the competing model and verify with `ollama ps` and `nvidia-smi`.

## Focused Test Gates

```bash
pytest -q tests/test_workflow_coherence_contract.py
pytest -q tests -m 'not live_model and not requires_ollama and not requires_gpu and not requires_supabase'
python -m py_compile .codex/mcp/ucore_context_server.py
```

## Dashboard

```bash
cd src/dashboard/unity-npc-llm-training-dashboard
npm run build
npm run dev
```

When changing dashboard request/response paths, verify backend schemas and rendered UI behavior.

