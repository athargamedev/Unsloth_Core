# Config Directory Structure

This directory is intentionally organized by **platform**, not by function.
Each platform folder manages its own communication: naming, credentials,
presets, and workflow participation.

## Layout

```text
etc/
├── README.md                        ← This file
├── env-reference.yaml               ← Maps .env vars to platform configs
│
├── npc-production-strategy.yaml     ← Pipeline profile defaults
├── parameter-registry.yaml          ← All registered parameters
├── eval-presets.yaml                ← Evaluation profiles
├── promotion-rules.yaml             ← Training quality gates
├── workload-policy.yaml             ← Local-vs-remote planning
│
├── presets/                         ← Training presets (shared across platforms)
│   ├── fast-3b.yaml
│   ├── safe-any.yaml
│   ├── smoke.yaml
│   ├── quality-1.7b.yaml
│   ├── premium-3b.yaml
│   ├── premium-8b.yaml
│   ├── remote-3b-quality.yaml
│   ├── wandb.yaml                   ← enables W&B logging
│   └── wandb_compare.yaml           ← W&B compare sweep config
│
├── ollama/                          ← Local generation + judge
│   └── config.yaml
├── ollama-model-presets.yaml        ← Legacy (content moved to ollama/)
│
├── wandb/                           ← Experiment tracking + hosted judge
│   ├── config.yaml
│   └── presets/
│       └── default.yaml
│
├── confident/                       ← Evaluation orchestration + tracing
│   ├── config.yaml
│   ├── classifiers_setup.md         ← Confident AI classifier specs
│   ├── classifiers_setup.json
│   └── presets/
│
├── huggingface/                     ← Base model config downloads
│   └── config.yaml
│
├── modal/                           ← Remote GPU (scaffolded, inactive)
│   ├── config.yaml
│   └── profiles/
│
├── llama.cpp/                       ← Local inference server
│   └── config.yaml
│
├── base_models/                     ← Cached HF config.json files
│   └── unsloth-Llama-3.2-3B-Instruct-bnb-4bit.json
│
├── lora-sft-base.yaml               ← Canonical base training config
└── model-presets.yaml               ← Model definitions
```

## Platform role summary

| Folder | Platform | Purpose | Active? |
|--------|----------|---------|---------|
| `presets/` | Training | Shared training configs | Yes |
| `ollama/` | Ollama | Local generation + judge | Yes |
| `wandb/` | W&B | Experiment tracking + hosted judge | Yes |
| `confident/` | Confident AI | Eval orchestration + tracing | Yes |
| `huggingface/` | HuggingFace Hub | Config downloads for export | Yes |
| `llama.cpp/` | llama.cpp | Local inference server | Yes |
| `modal/` | Modal | Remote GPU (future) | No (scaffolded) |

## How to use

Each platform config YAML follows the same structure:
- `## role` — what the platform does (runs work vs logs results)
- `## credentials` — which env vars provide keys
- `## naming` — naming conventions expected by the platform
- `## workflow` — which pipeline stages use the platform

The `env-reference.yaml` file maps every `.env` variable to its platform
config entry, so you can trace "which platform needs which env var".
