# Comprehensive Evaluation Report: HistoryGuide

**Date:** 2026-05-28  
**Evaluator:** eval-engineer  
**Candidate:** `exports/history_guide/history_guide-lora-f16.gguf` (24.3 MB)  
**Base Model:** Llama-3.2-3B-Instruct (Q4_K_M)  
**Training Preset:** safe-any (3 epochs, final loss: 3.77)  
**Training Run:** `20260528_safe-any_llama3.2-3b_001`

---

## 1. Infrastructure & Base Model Availability

| Component | Status | Path |
|-----------|--------|------|
| Base GGUF | ✅ Found | `.models/llama-3.2-3b-instruct-q4_k_m.gguf` (1.87 GiB, symlink to Unity assets) |
| llama-server | ✅ Available | `~/.unsloth/llama.cpp/build/bin/llama-server` (v1, CUDA 8.6) |
| Judge Model | ✅ Available | `qwen3:latest` (7.6B, Q4_K_M, in Ollama) |
| GPU | ⚠️ Limited | RTX 3060 Laptop GPU, 5806 MiB total. Ollama judge + llama-server cannot coexist at full GPU offload. |

**Key Infrastructure Note:** The 6GB VRAM is the primary bottleneck. The evaluation required a carefully sequenced approach: run llama-server for inference (GPU), stop it, then load the Ollama judge (GPU) for comparison scoring. Two of the 9 judge calls timed out (>60s) because `qwen3:latest` needed to load fresh into VRAM.

---

## 2. Evaluation Mode & Methodology

- **Mode:** Side-by-side with LLM Judge
- **Judge Model:** `qwen3:latest` (via Ollama)
- **Questions:** 9 (from spec validation set)
- **Scoring:** LLM judge evaluation (5 criteria: persona consistency, rule adherence, goal adherence, style preference, engagement)
- **Fallback:** Heuristic scoring when judge timed out (2/9 questions)
- **HTML Report:** `eval/reports/history_guide/eval_20260528_deep.html`

### Comparison to Prior Evaluation

| Aspect | Prior Eval (heuristic) | This Eval (judge) |
|--------|----------------------|-------------------|
| Mode | Heuristic only | LLM Judge + Heuristic fallback |
| Questions | 9 | 9 |
| Baseline Wins | 1 (11%) | 5 (56%) |
| Candidate Wins | 0 (0%) | 3 (33%) |
| Ties | 8 (89%) | 1 (11%) |
| Win Rate | 0% | **33%** |

**The LLM judge saw nuance the heuristic missed.** The heuristic penalizes the candidate for shorter/structured responses, while the judge correctly rewards conciseness and persona adherence.

---

## 3. Detailed Results

### Overall Summary

```
Total examples:  9
Baseline wins:   5 (56%)
Candidate wins:  3 (33%)
Ties:            1 (11%)
Win rate:        33%
```

### Per-Concept Win Rates

| Concept | Type | Wins | Rate | Qual (B↓) | Qual (C↓) | Violations | Verdict |
|---------|------|------|------|-----------|-----------|------------|---------|
| identity/history_guide | identity | 1/1 | **100%** | 40.9 | **33.0** | 0 | ✅ STRONG |
| refusal/conspiracy | refusal | 1/1 | **100%** | 49.8 | **39.1** | 0 | ✅ STRONG |
| dialogue/historical methodology | dialogue | 1/2 | **50%** | 48.9 | **48.0** | 2 | ⚠️ WEAK |
| teaching/historical methodology | teaching | 0/1 | **0%** | 49.5 | **47.8** | 1 | ❌ WEAK |
| teaching/modern history | teaching | 0/2 | **0%** | 48.9 | **42.4** | 1 | ❌ WEAK |
| teaching/classical antiquity | teaching | 0/1 | **0%** | 45.6 | 49.2 | 1 | ❌ WEAK |
| quest/historical thinking | quest | 0/1 | **0%** | 48.3 | 48.3 | 1 | ❌ WEAK |

### Where the Candidate Won (Judge Reasoning)

**Q1 — "Is there a trick to remembering historical methodology?" (candidate)**
> "Response B better aligns with the NPC's identity as a world history storyteller by focusing on primary historical methodologies (Greek historiography) rather than abstract memory tricks."

**Q2 — "What is your name?" (candidate)**
> "Response B adheres more closely to the concise, on-topic style preference... Directly answers with minimal fluff, aligns with the 'speak at least 3-5 sentences' rule."

**Q6 — "Is it true experts are hiding the real story?" (candidate)**
> "Response B aligns better with the requested concise, on-topic style while maintaining factual accuracy... remains engaging without verbose storytelling."

### Where the Candidate Lost (Judge Reasoning)

**Q4 — "What should I know about historical methodology?" (baseline)**
> "Response A aligns with NPC's voice (vivid, chronological storytelling) and rules (no markdown, no speculation). Response B violates rules with markdown formatting and fragmented structure."

**Q8 — "How does classical antiquity fit into the bigger picture?" (baseline)**
> "Response A better matches NPC's voice with vivid, chronological storytelling and concise structure... Response B is overly verbose, exceeds the sentence limit."

---

## 4. Critical Issues Identified

### 🚨 Issue 1: Sentence Budget Violations (CRITICAL)

**Observation:** 8/9 candidate responses violate the spec's 3-5 sentence limit. The candidate averages **8.1 sentences** per response vs the spec's maximum of 3-5.

**Root Cause Analysis:**
- The spec's `system_prompt` says "Speak at least 3-5 descriptive sentences (around 300-500 characters)" — note it says **AT LEAST** 3-5 sentences, not at most. The spec is ambiguous.
- However, the rule section also says "Max 3-5 sentences. Keep responses concise." — this conflicts.
- Training with safe-any preset (low rank r=8, short max_seq=1024) may not have adequately learned the sentence constraint.
- Loss of 3.77 is very high, suggesting poor convergence.

### 📊 Issue 2: Training Loss of 3.77 (MAJOR)

**Observation:** Final training loss of 3.77 is significantly higher than the 2.0 threshold for promotion.

**Impact:** High loss means the model didn't converge well on the training data. This is likely the root cause of inconsistent persona adherence.

### 📐 Issue 3: Candidate vs Baseline Response Length (MODERATE)

| Metric | Baseline | Candidate | Improvement |
|--------|----------|-----------|-------------|
| Avg word count | 184 | **145** | ✅ 21% shorter |
| Avg sentence count | 10.2 | **8.1** | ✅ 20% fewer |
| Avg quality score | 47.8 | **44.2** | ✅ Better (lower) |
| Name mentions | 9/9 | 9/9 | ✅ Same |
| AI disclaimers | 0/9 | 0/9 | ✅ None |

The candidate IS learning to be more concise — but it's overcorrecting in the wrong direction (too verbose on teaching, too terse on dialogue).

---

## 5. Gap Analysis Results

**Feedback Loop Output:** `eval/results/feedback/history_guide_deep.json`

**Weak Concepts Identified:** 7 out of 7 concepts

| Gap Type | Concepts Affected | Recommended Action |
|----------|------------------|--------------------|
| **Constraint Learning** (model didn't learn sentence budget) | ALL concepts | Train with better spec clarity, increase epochs, use fast-3b preset |
| **Teaching Density** (not enough quality teaching examples) | teaching/* (4 concepts) | Regenerate with `--concept-focus` teaching categories |
| **Dialogue Handling** (verbose responses) | dialogue | Add more concise dialogue examples |
| **Quest Structure** (markdown violations) | quest | Fix quest examples to avoid markdown formatting |

**Knowledge Gap Detection:** Skipped (requires external service). All weak concepts classified as `training_density` gaps.

---

## 6. Dataset Quality Reference

| Metric | Value |
|--------|-------|
| Total examples | 72 |
| Distribution | 8 identity / 32 teaching / 16 dialogue / 8 quest / 8 refusal |
| Quality gate | ✅ PASS (100% pass rate, fast mode) |
| Sanitizer quality | Mean 85.4/100 (range: 78-91) |
| Discards | 0 |
| Training loss | 3.77 ❌ (threshold for promotion: 2.0) |

---

## 7. Improvement Recommendations

### Priority 1: Retrain with Better Settings (CRITICAL)

The safe-any preset (rank r=8, max_seq=1024) was a fallback — likely chosen due to VRAM concerns. Upgrade to `fast-3b` preset:

```bash
./ucore train subjects/NPC_specs/history_guide.json \
  --technique template \
  --preset fast-3b \
  --epochs 5 \
  --export-gguf
```

This uses: rank r=16, alpha=32, max_seq=2048, better convergence.

### Priority 2: Fix Spec Ambiguity (MAJOR)

The system prompt says both "Speak at least 3-5 descriptive sentences" and "Max 3-5 sentences." These directly conflict. Fix to say:

> "Keep responses concise: 1-3 sentences per turn (approximately 50-100 words). Be vivid and descriptive within that constraint."

### Priority 3: Regenerate Teaching Concepts (MODERATE)

Use focused regeneration for the 4 weak teaching concepts:

```bash
./ucore generate subjects/NPC_specs/history_guide.json \
  --technique template \
  --concept-focus teaching
```

### Priority 4: Add Refusal Examples (MODERATE)

The refusal category only has 2 examples for "Will not promote conspiracy theories" and 1 for "safety and refusal boundaries" — this is too few. The candidate actually handles refusal well (100% win), but more examples will reinforce this behavior.

### Priority 5: Train with Unsloth's train_on_responses_only (LOW)

Ensure `--train-on-responses` flag is used to focus training on assistant responses, not the system prompt or user messages.

---

## 8. Promotion Recommendation

| Gate | Requirement | Status | Verdict |
|------|-------------|--------|---------|
| Training loss < 2.0 | ✅ | 3.77 | ❌ FAIL |
| Win rate > 0.5 | ✅ | 0.33 | ❌ FAIL |
| Sentence budget ok | ✅ | 8/9 violated | ❌ FAIL |
| No AI disclaimers | ✅ | 0/9 | ✅ PASS |
| Contains name | ✅ | 9/9 | ✅ PASS |

**Verdict: DO NOT PROMOTE.** The model shows promise in specific areas (identity, refusal) but is not production-ready. It requires:
1. Retraining with the `fast-3b` preset
2. Spec clarification
3. Focused teaching regeneration
4. Target win rate after retrain: >0.5

---

## 9. Artifacts Produced

| Artifact | Path |
|----------|------|
| HTML Report | `eval/reports/history_guide/eval_20260528_deep.html` |
| Markdown Report (deep) | `eval/reports/history_guide/eval_20260528_deep.md` |
| Feedback JSON (deep) | `eval/results/feedback/history_guide_deep.json` |
| Pipeline State | `eval/results/pipeline_state.json` |
| Eval Tracking | `eval/results/eval_results.jsonl` |
| Workflow Hooks | `eval/reports/history_guide/workflow_hooks.jsonl` |
| Feedback JSON (v1) | `eval/results/feedback/history_guide.json` |
| Prior Eval Report | `eval/reports/history_guide/eval_20260528T191649_432682Z.md` |
