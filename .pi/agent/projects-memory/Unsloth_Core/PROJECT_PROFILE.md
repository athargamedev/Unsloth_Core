# Unsloth_Core Project Profile

## Mission

Produce high-quality GGUF LoRA adapters for Llama 3.2 3B NPCs that Unity/LLMUnity can load at runtime, with local Supabase supporting dialogue/session infrastructure.

## Canonical Entry Points

- CLI: `./ucore`
- Agent source of truth: `AGENTS.md`
- Main docs: `README.md`, `docs/TRAINING_WORKFLOW_CONTEXT.md`
- Modular backend: `server-modular.ts`, `src/backend/`
- Frontend dashboard: `frontend_control/`, `src/components/`, `src/hooks/`, `src/stores/`

## Pipeline

1. Validate spec: `./ucore validate-spec <spec> --generation-ready`
2. Generate dataset: `./ucore generate <spec> --technique template|docs|ollama|openai|anthropic`
3. Sanitize: `./ucore sanitize <train.jsonl> --output <train_clean.jsonl> --strict-canonical --require-complete-metadata`
4. Dataset gate: `./ucore dataset-eval <spec> --technique <technique> --mode fast --judge-model qwen3:latest`
5. Train: `./ucore train <spec> --technique <technique> --preset smoke|fast-3b|safe-any --export-gguf`
6. Evaluate: `./ucore evaluate --baseline <gguf> --spec <spec> --report-html`
7. Feedback: `./ucore feedback <spec> ...`

## Hard Rules

- Prefer `./ucore` over direct script calls.
- Do not lower dataset thresholds or delete rows to force quality gates to pass.
- Fix generation, prompts, primers, concepts, or generated rows when DeepEval fails.
- Training is blocked unless a fresh passing `quality_summary.json` matches the sanitized dataset hash, unless explicitly bypassed with `--allow-ungated-dataset`.
- Do not use feedback `--auto-retrain` with LLM-grounded generation on RTX 3060 6GB; unload Ollama before manual training.
- Use modular backend (`npm run dev:modular`) for new dashboard/backend work.

## Runtime Notes

- Python env: `source unsloth_env/bin/activate`
- Local Ollama judge default: `qwen3:latest`
- llama.cpp tools: `~/.unsloth/llama.cpp/`
- Adapter GGUF naming: `exports/{npc_key}/{npc_key}-lora-f16.gguf`
- NPC keys are `snake_case`.
