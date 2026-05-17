# Remote Compute Strategy v2

Based on research and user feedback: skip Kaggle/Colab, focus on what's already working.

## Key Findings

| Service | Status | Verdict |
|---------|--------|---------|
| **W&B** | Already logged in, used by `--wandb` flag | Use on EVERY pipeline run — eval now logs Tables + per-category metrics |
| **PeerLM** | 200 credits available, account ready | Blind eval across 200+ models → professional reports |
| **OpenPipe ART** | v0.5.17 installed in unsloth_env, uses W&B API key | Serverless GPU via W&B credits, but only supports Qwen models for remote training. Llama works locally only. |
| **Kaggle** | Bad experiences with VSCode extensions | Skip |
| **Colab** | Bad experiences | Skip |

## Architecture

### Stays Local (no changes needed)
- Onyx RAG generation (subjects/)
- Dataset sanitization
- SFT LoRA training with Unsloth (~60s/NPC, already fast)
- GGUF export (adapter mode)
- Unity deployment (StreamingAssets)
- `ucore` CLI (orchestration hub)

### Remote Layer (adds professional polish)
- **W&B** on every train + eval run → shareable reports with metrics, charts, artifacts
- **PeerLM** for blind evaluation → structured JSON showing where our NPCs rank vs GPT-4, Claude, Gemini
- **OpenPipe ART** (exploratory) → RL training for NPC behavior refinement, using W&B credits

## Phase 1: W&B on Every Pipeline Run (Week 1)

**Goal:** Every `ucore pipeline` (or train + evaluate) call auto-logs to W&B with proper grouping.

### Current state
- `ucore train --wandb` already logs: loss curves, config snapshot, dataset/LoRA/GGUF artifacts
- `ucore evaluate` has NO W&B integration — writes HTML/markdown locally only
- No W&B Reports being generated

### What to build

**1a. Add `--wandb` to evaluate.py**
- Log per-question scores as a **W&B Table** (sortable, filterable in the UI)
- Schema: `[question, baseline_score, candidate_score, category, concept, verdict(win/lose/tie)]`
- Log overall metrics: `eval/win_rate`, `eval/baseline_avg`, `eval/candidate_avg`
- Group eval runs under the same W&B Run as the training that produced them (use `--run-id` or auto-detect from artifact metadata)

```python
# Example: what the W&B table looks like in the UI
wandb.log({
    "eval/comparison_table": wandb.Table(
        columns=["question", "category", "concept", "baseline", "candidate", "verdict"],
        data=[
            ["What is your name?", "identity", "self_intro", 0.8, 0.9, "win"],
            ...
        ]
    ),
    "eval/win_rate": 0.58,
    "eval/total_questions": 16,
})
```

**1b. Link eval to training runs**
- When running `ucore pipeline`, share a single W&B run across generate → train → export → eval stages
- Or: use W&B Run grouping so eval appears as a child of the training run
- Use `WANDB_RUN_ID` env var or pass `--wandb-run-id` from train to eval

**1c. Create a W&B Report Template**
- W&B Reports are rich markdown docs with live embedded charts
- Template "NPC Training Report" includes:
  - NPC name, system prompt, technique
  - Training loss curve (live from W&B)
  - Eval comparison table + win rate
  - Dataset artifact link
  - LoRA + GGUF artifact links
  - Training config summary
- Saved as a template — duplicate for each new NPC run
- Shareable URL — send to employers

**Files to modify:**
- `scripts/evaluate.py` — add `--wandb` flag, Table logging
- `scripts/train.py` — improve artifact metadata (store NPC name, technique, preset)
- Possibly `ucore` CLI — thread W&B run ID through the pipeline stages

### Job-seeking value
Share W&B Report links like: "wandb.ai/andreabenathar-twl-games/unsloth-core/reports/History-Guide-Round-3"

---

## Phase 2: PeerLM Blind Evaluation (Week 1-2)

**Goal:** Export our NPC eval prompts to PeerLM, run blind ranking, import results.

### How PeerLM works (from docs)
- Create a "project" with system prompts and test questions
- Select models to compare (200+ available: GPT-4o, Claude Sonnet 4, Gemini 2.5, Llama 3.1, Qwen, DeepSeek, etc.)
- PeerLM runs blind — models see anonymized prompts, responses shuffled
- Results: structured JSON with per-model scores, per-question breakdowns, rankings
- Free for individuals (200 credits to start)

### What to build

**2a. Export script: `scripts/peerlm/export_prompts.py`**
- Reads evaluation prompts from `eval/` or NPC spec
- Organizes them by category (identity, teaching, dialogue, quest, refusal)
- Maps each category to a PeerLM "persona" with specific criteria
- Outputs PeerLM-compatible JSON

**2b. Import script: `scripts/peerlm/import_results.py`**
- Reads PeerLM JSON export
- Converts to W&B Table format (or CSV/markdown)
- Generates comparison: "Where does Llama 3.2 3B (our base) rank vs competitors?"
- Note: PeerLM evaluates models on the PeerLM platform, not our LoRAs directly
- Useful comparison: "Does our fine-tuned SFT model beat the base model?" — we answer locally. "How does our approach compare to GPT-4 on NPC dialogue?" — PeerLM answers this.

**2c. PeerLM → W&B pipeline**
- After local eval gives us "NPC v2 wins against NPC v1"
- PeerLM gives us "NPC (Llama 3.2 3B SFT) ranks in top 30% vs all models on persona adherence"
- Combine both in a single W&B Report for maximum impact

**What to evaluate with PeerLM:**
- NPC system prompts + test questions
- Categories: identity accuracy, teaching quality, dialogue fluency, quest adaptability, refusal safety
- Models to test: GPT-4o, Claude Sonnet 4, Gemini 2.5 Pro, Llama 3.2 3B (our base), Llama 3.1 8B, Qwen 3 14B, DeepSeek V3
- Our NPC's base model (Llama 3.2 3B) + our SFT LoRA output (export prompts to compare)

### Job-seeking value
"Third-party blind evaluation ranked my fine-tuned 3B NPC model competitively with GPT-4 on domain-specific dialogue tasks."

---

## Phase 3: OpenPipe ART Exploration (Week 2-3)

**Goal:** Understand what ART can do for us, especially with W&B credits for remote GPU.

### What ART is
- OpenPipe's **Agent Reinforcement Training** framework
- Uses **GRPO** (Group Relative Policy Optimization) to train LLMs as agents
- Two backends:
  - `LocalBackend` — trains on local GPU (our 6GB RTX 3060)
  - `ServerlessBackend` — trains on W&B Training cluster (uses W&B credits)
- Supports our models: Llama 3.2 3B is in their tested list
- **Limitation:** ServerlessBackend only supports Qwen 3 14B and Qwen 3 30B-A3B for REMOTE training. For Llama models, you use LocalBackend (same local GPU).

### What this means for us
| Scenario | Works? | Notes |
|----------|--------|-------|
| Train Llama 3.2 3B locally with ART | Yes | Same GPU as Unsloth, but ART does RL not SFT |
| Train Llama 3.2 3B remotely (W&B credits) | No | Serverless doesn't support Llama models yet |
| Train Qwen 3 14B remotely (W&B credits) | Yes | Would use W&B credits for GPU time |
| Use ART to RL-refine our Unsloth SFT model | Yes | Export Unsloth LoRA → load in ART → RL train → export back |

### Practical next steps
1. Run ART's quickstart (2048 game with Qwen 3 14B on ServerlessBackend) to understand:
   - How W&B credits are consumed
   - How training works end-to-end
   - What metrics/traces look like
2. If it works well: explore adapting our NPC pipeline
   - Train a Qwen-based NPC (not Llama) with ART + ServerlessBackend (remote GPU)
   - Compare quality vs our Unsloth Llama SFT models
3. Don't force it — ART is RL, our current pipeline is SFT. They serve different purposes.

### Job-seeking value
Medium — ART is cutting-edge (GRPO), but not directly applicable to our Llama 3.2 Unity workflow yet.

---

## Summary: What We Build

| Priority | What | Service | Effort | Impact |
|----------|------|---------|--------|--------|
| **P0** | `evaluate.py --wandb` with Tables | W&B | 1-2 days | High — every run tracked, shareable |
| **P0** | W&B Report template | W&B | 1 day | High — portfolio-ready reports |
| **P1** | PeerLM export/import scripts | PeerLM | 2-3 days | High — third-party validation |
| **P2** | ART quickstart + evaluation | OpenPipe | 1-2 days | Medium — learn if RL helps NPCs |
| **X** | Kaggle integration | Kaggle | Skip | Bad prior experience |
| **X** | Colab integration | Colab | Skip | Bad prior experience |

## Quick-Start

- [ ] Verify W&B works: `wandb login --verify`
- [ ] Create PeerLM account at peerlm.com, check credits
- [ ] Verify ART install: `python3 -c "from art import TrainableModel; from art.serverless.backend import ServerlessBackend; print('OK')"`
- [ ] Phase 1: Add `--wandb` to evaluate.py
- [ ] Phase 1: Run `./ucore train --wandb && ./ucore evaluate --wandb` for one NPC
- [ ] Phase 1: Create W&B Report in the web UI, save as template
- [ ] Phase 2: Write PeerLM export script
- [ ] Phase 2: Run first PeerLM evaluation
- [ ] Phase 2: Import PeerLM results into W&B
- [ ] Phase 3: Run ART quickstart (Qwen 3 14B, 2048 game)
- [ ] Phase 3: Decide if ART applies to our NPC pipeline

## Decision Points

1. **Start with Phase 1 (W&B on every run) first?** — It's the highest ROI and builds on existing integration.
2. **PeerLM: test just frontier models or also open-source?** — Frontier (GPT-4, Claude, Gemini) gives job-market credibility. Open-source gives us scientific baselines.
3. **ART: explore now or defer?** — It's installed and could eventually do RL for NPC behaviors, but the Llama remote GPU gap means it won't solve our immediate compute bottleneck.

---

## Implementation Status

### Completed (this session)
- ✅ **Automated Onyx-LLM Feedback Loop Fix** — Repaired bug where Ollama flag overrode Onyx generation technique, allowing the pipeline to correctly rewrite Onyx context into multi-turn JSONL examples.
- ✅ **VRAM Workaround for Feedback Loop** — Defined the sequential pipeline strategy for 6GB GPUs: generated dataset via `ucore feedback --auto`, manually unloaded `llama3.1:latest` (`curl ... keep_alive: 0`), then trained.
- ✅ **Round 5 Chef Assistant Retraining** — Addressed 8 weak concepts, dropping training loss to 1.0746. Evaluated with 100% tie/win rate vs previous v2 baseline. Exported updated `chef_assistant-lora-f16.gguf` to LLMUnity.
- ✅ **Round 3 History Guide Retraining** — Addressed 9 weak concepts, achieving training loss of 1.1444. Exported updated `history_guide-lora-f16.gguf` to LLMUnity.
- ✅ **evaluate.py --wandb** — Added W&B Table logging with per-question breakdown, per-category win rates, and improved run metadata. Replaced flat per-step logging with structured Table.
- ✅ **Updated CLI reference** — Documented all evaluate flags (--wandb, --wandb-project, --wandb-entity, --judge, --report-html, --track, --feedback-json)
- ✅ **Fixed llama-server readiness** — Server now probes HTTP `/v1/models` endpoint instead of just TCP socket, preventing 503/HTTP timeout errors during eval.
- ✅ **wb_report.py** — Script to generate portfolio-ready markdown reports from W&B data via the API.
- ✅ **peerlm/export.py** — Script to export NPC evaluation prompts in PeerLM-compatible JSON format (5 persons per NPC, 25 test questions, 9 recommended models).
- ✅ **peerlm/import.py** — Script to import PeerLM exported JSON results and optionally log them to W&B as Tables.
- ✅ **Deprecation fixes** — `datetime.utcnow()` replaced with `datetime.now(datetime.UTC)` across evaluate.py, wb_report.py, peerlm/export.py.

### Next Steps
- [ ] Create W&B Report template in web UI (instructions in Quick-Start below)
- [ ] Run PeerLM evaluation for all 3 NPCs (use exported prompts, compare vs recommended models)
- [ ] Run `python scripts/wb_report.py` after each new eval to generate portfolio reports
- [ ] Explore ART quickstart (2048 game with Qwen 3 14B on ServerlessBackend)
