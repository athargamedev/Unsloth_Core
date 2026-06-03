# NPC Creation Playbook

> Legacy quick-start playbook. For production strategy, presets, gates, and anti-loop policy, use `docs/planning/npc-gguf-production-strategy.md` first.
> Optimized for RTX 3060 6 GB | Qwen3-1.7B | Ollama technique
> Production-ready NPC in ~5 minutes of active work

---

## Prerequisites

```bash
source unsloth_env/bin/activate

# VRAM check — if free VRAM is below ~5 GB, stop Ollama
nvidia-smi --query-gpu=memory.free --format=csv,noheader

# Stop Ollama to free ~4 GB VRAM for training
sudo systemctl stop ollama

# Verify the base GGUF is available for evaluation
find ~/.cache/huggingface/hub/models--unsloth--Qwen3-1.7B-GGUF -name '*.gguf' 2>/dev/null || echo "Pull it: huggingface-cli download unsloth/Qwen3-1.7B-GGUF --local-dir ~/.cache/huggingface/hub/models--unsloth--Qwen3-1.7B-GGUF"
```

---

## Pipeline (Fast Track — 7 Steps)

### Step 1: Create NPC Spec

```bash
./ucore init <npc_key> --subject "<subject>"
```

This creates the spec at `subjects/NPC_specs/<npc_key>.json` and a primer stub at `subjects/reference_docs/<npc_key>_primer.md`.

**Critical spec rules:**

- **System prompt**: 4-section LLMUnity format required: `IDENTITY | VOICE | KNOWLEDGE | RULES`
- **Sentence/character consistency**: `dialogue.max_sentences` and `dialogue.max_characters` in the structured config **must match** any text about sentence/character limits in the system prompt. These are two sources of truth — one source must drive both.
- **Minimum 5 categories** with these counts:
  | Category | Minimum Examples | Purpose |
  |----------|-----------------|---------|
  | `identity` | 8 | Personality, background, mannerisms |
  | `teaching` | 32 | Subject-matter explanations |
  | `dialogue` | 16 | Multi-turn conversation handling |
  | `quest` | 8 | Scenario-based interactions |
  | `refusal` | 8 | Safety boundary responses |
  | **Total** | **72** | |
- **Validate before proceeding**:
  ```bash
  ./ucore validate-spec subjects/NPC_specs/<npc_key>.json --generation-ready
  ```

### Step 2: Generate Dataset (Ollama Preferred)

```bash
./ucore generate subjects/NPC_specs/<npc_key>.json --technique ollama
```

- **Expected output**: 72–104 ChatML-format examples
- **Generator model**: `qwen2.5:7b` (default) or `qwen3:latest`
- **Output path**: `subjects/datasets/<npc_key>/ollama/train.jsonl`
- **Duration**: ~1–2 minutes

**Fallback to template** (faster, fewer examples):

```bash
./ucore generate subjects/NPC_specs/<npc_key>.json --technique template
```

- Output: 72 examples, deterministic, no external LLM needed
- Use for smoke tests or narrow knowledge domains

**Expected results by technique:**

| Technique | Rows | Category Coverage | Eval Loss (typical) | Best For |
|-----------|------|-------------------|---------------------|----------|
| template | 72 | Exact minimums, uniform | 1.2–2.5 | Small domains, debugging |
| ollama | 104 | 2x identity/refusal, richer variety | 1.2–2.0 | Production NPCs, complex domains |

### Step 3: Sanitize

```bash
./ucore sanitize subjects/datasets/<npc_key>/ollama/train.jsonl \
  --output subjects/datasets/<npc_key>/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
```

Sanitization fixes:
- AI disclaimer artifacts ("As an AI", "I cannot", etc.)
- Whitespace and formatting inconsistencies
- Empty or truncated messages
- Validates ChatML structure and canonical format
- Removes entries that fail metadata completeness checks

### Step 4: Quality Gate

```bash
./ucore dataset-eval subjects/NPC_specs/<npc_key>.json \
  --technique ollama --mode fast
```

- Uses DeepEval with `qwen3:latest` as the judge (local Ollama)
- Checks persona fit, category coverage, and training usefulness
- Writes `quality_summary.json` and `quality_failures.json` beside the dataset
- **Training is blocked** unless the gate passes (opt out with `--allow-ungated-dataset`)
- `--mode fast`: sampled eval, diagnostics only
- `--mode release`: strict full gate, required for production pipelines

### Step 5: Train

```bash
./ucore train subjects/NPC_specs/<npc_key>.json \
  --from-spec --technique ollama \
  --model unsloth/Qwen3-1.7B-unsloth-bnb-4bit \
  --preset fast-1.7b --export-gguf
```

**Expected results:**

| Metric | Expected Range | Notes |
|--------|---------------|-------|
| Training loss | 2.5–4.0 | Varies by dataset complexity and domain size |
| Eval loss | 1.2–2.5 | **<2.0 = good convergence.** <1.5 = excellent |
| Training time | 40–60 seconds | Qwen3-1.7B, 3 epochs, 1024 max_seq |
| GGUF size | ~34 MB | Adapter only (LoRA weights in f16) |
| VRAM usage | ~3.4 GB | Leaves ~2 GB headroom on 6 GB GPU |

**Check the log for this message — if missing, `train_on_responses_only` is not active:**

```
Applying train_on_responses_only
```

**Output artifact:** `exports/<npc_key>/<npc_key>-lora-f16.gguf`

### Step 6: Evaluate

```bash
# Locate the base GGUF (auto-downloaded by HF hub)
BASE_GGUF=$(find ~/.cache/huggingface/hub/models--unsloth--Qwen3-1.7B-GGUF -name '*.gguf' | head -1)

./ucore evaluate --candidate exports/<npc_key>/<npc_key>-lora-f16.gguf \
  --base-model "$BASE_GGUF" \
  --spec subjects/NPC_specs/<npc_key>.json \
  --judge --report-html
```

- Uses `llama-server --lora` to evaluate the adapter without full-merging
- Same mechanism as the LLMUnity runtime
- Generates an HTML report with Chart.js visualizations

**Win rate guidance:**

| Win Rate | Assessment |
|----------|-----------|
| < 30% | Poor — revisit dataset or training configuration |
| 30–50% | Below average — dataset gaps likely |
| 50–70% | Good — meets baseline expectations |
| **> 70%** | **Excellent — production ready (reference: history_guide hit 78%)** |

### Step 7: Record Run

Add an entry to the run comparison table at `eval/results/run_comparison_table.json`:

```json
{
  "run_id": "YYYYMMDD_fast-1.7b_qwen3-1.7b_XXX",
  "npc_key": "<npc_key>",
  "model": {
    "architecture": "qwen3",
    "params": "1.7B"
  },
  "preset": {
    "name": "fast-1.7b",
    "lora_r": 16,
    "lora_alpha": 32
  },
  "dataset": {
    "technique": "ollama",
    "num_examples": 104
  },
  "train_on_responses_only": true,
  "results": {
    "training_loss": 3.474,
    "eval_loss": 1.808
  }
}
```

---

## Preset Quick Reference

| Preset | LoRA r | α | max_seq | grad_accum | Epochs | When to Use |
|--------|--------|---|---------|------------|--------|-------------|
| `safe-any` | 8 | 16 | 1024 | 8 | 3 | Conservative fallback. Any model, any VRAM. |
| **`fast-1.7b`** | **16** | **32** | **1024** | **4** | **3** | **Qwen3-1.7B on 6 GB VRAM — RECOMMENDED** |
| `fast-3b` | 16 | 32 | default | 8 | 3 | 3B models on 10 GB+ VRAM. Auto-downgrades if <10 GB. |
| `smoke` | 8 | 16 | 512 | 4 | 1 | Debug and test runs only. One epoch, fast iteration. |
| `premium-3b` | 32 | 64 | default | 8 | 3 | Quality runs on remote/cloud hardware with ample VRAM. |

**Dimensional fit (RTX 3060 6 GB):**

```
safe-any   r=8  α=16  max_seq=1024  ← fits any model, low LoRA capacity
fast-1.7b  r=16 α=32  max_seq=1024  ← fits Qwen3-1.7B, 2x LoRA capacity ✓
fast-3b    r=16 α=32  max_seq=full  ← OOM on 6 GB, needs 10 GB+
```

---

## Expected Results Reference

| NPC | Technique | Rows | Train Loss | Eval Loss | Win Rate | Verdict |
|-----|-----------|------|-----------|-----------|----------|---------|
| history_guide | template | 72 | 4.176 | 2.464 | 78% | Good — borderline eval loss, strong win rate |
| history_guide | ollama | 104 | 3.474 | 1.808 | — | Best — eval loss below 2.0 threshold |
| chef_assistant | template | 72 | 2.479 | 1.156 | — | Excellent — narrow domain, strong convergence |

Use these as sanity checks: if your numbers diverge significantly (e.g., eval loss > 3.5 or win rate < 30%), revisit the dataset quality or check `train_on_responses_only` is active.

---

## Key Learnings (Must Read Before First NPC)

1. **Stop Ollama before training.** `sudo systemctl stop ollama` frees ~4 GB VRAM. Running Ollama in the background guarantees VRAM contention. Restart with `sudo systemctl start ollama` after training.

2. **`train_on_responses_only` must be verified per run.** Check the training log for the line `"Applying train_on_responses_only"`. If it's missing, loss values are inflated by 1.0–1.5 points because the model trains on instruction tokens too.

3. **Cross-architecture loss is NOT comparable.** Qwen3 tokenizer produces different loss scales than Llama-3.x tokenizer. Only compare eval loss within the same model family.

4. **Eval loss is the true quality signal.** Training loss is inflated by prompt tokens even with response-only masking (due to sequence packing). Watch eval loss — target <2.0 for good convergence, <1.5 for excellent.

5. **Template datasets are sufficient for narrow domains.** Chef assistant (culinary arts, ~5 topics) hit 2.479/1.156 with template alone. History guide (broad world history) needed Ollama enrichment to cross the eval loss threshold.

6. **Spec consistency matters.** The system prompt text and the structured `dialogue` config must agree on sentence and character limits. A 4x discrepancy was found in the chef_assistant spec — the system prompt said 200 characters but the config allowed 800.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| CUDA OOM at model load | Insufficient VRAM | Check `nvidia-smi`. Stop Ollama. Try `safe-any` preset. |
| CUDA OOM during training | `max_seq` too high for available VRAM | Reduce `max_seq` to 1024. Lower `gradient_accumulation_steps`. |
| Training loss ~4.0+ even after first epoch | `train_on_responses_only` not active | Check logs for the confirmation message. Verify the fix is deployed. |
| Eval loss > training loss | Overfitting | Reduce epochs from 3 to 2. Increase dataset size. |
| GGUF export fails | Missing llama.cpp toolchain | Verify `~/.unsloth/llama.cpp/convert_lora_to_gguf.py` exists. |
| `llama-server --lora` fails | Wrong base model GGUF | Use the matching Qwen3-1.7B GGUF, not a Llama GGUF. |
| Dataset gate blocks training | Quality metrics below threshold | Fix dataset generation, don't lower thresholds. Pass `--allow-ungated-dataset` for development iteration only. |
| Preflight auto-downgrades to `safe-any` | VRAM < 10 GB (expected on 6 GB card) | This is normal. Use `fast-1.7b` with Qwen3-1.7B explicitly. |

---

## Quick Reference: CLI Flags

| Flag | Used With | Effect |
|------|-----------|--------|
| `--allow-ungated-dataset` | `train` | Bypass the dataset quality gate (dev iteration only) |
| `--skip-dataset-eval` | `feedback` | Skip DeepEval before retraining |
| `--deepeval-soft-fail` | `dataset-eval` | Run eval but continue even on failures |
| `--no-auto-unload-ollama` | `train`, `dataset-eval` | Don't stop Ollama automatically |
| `--full-merge` | `export` | Export merged GGUF (not adapter-only) |
| `--report-html` | `evaluate` | Generate Chart.js HTML evaluation report |
| `--judge-model` | `evaluate`, `dataset-eval` | Override the judge model (default: `qwen3:latest`) |

---

## Architecture Notes

For Unity/LLMUnity runtime deployment:

- **Base model (once)**: `Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf` — this is the current Unity base. Switch to Qwen3-1.7B base GGUF for optimal compatibility.
- **Adapter (many)**: Each NPC gets a ~34 MB LoRA GGUF. Unity loads the base model once and swaps adapters + system prompts per NPC.
- **Runtime eval**: `llama-server` with `--lora` flag — same mechanism as LLMUnity. No full-merge needed at runtime.
