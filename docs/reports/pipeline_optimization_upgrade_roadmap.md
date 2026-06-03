# Pipeline Optimization & Upgrade Roadmap (Phase 5)

**Author:** Build Orchestrator Agent (opencode)
**Date:** 2026-06-03
**Status:** COMPLETE (Final Synthesis Phase)

---

## Executive Summary

This Master Synthesis Roadmap outlines the prioritized plan for optimizing the `Unsloth_Core` dataset generation, sanitization, quality gating, training, and evaluation pipeline. 

By systematically addressing the technical bottlenecks and stubs identified during our stage-by-stage audits, we can:
1. **Reduce total DeepEval quality gate execution from 10 minutes to ~2.5 minutes** (a 4x speedup).
2. **Increase local training VRAM headroom by 0.5 GB**, ensuring robust local training on RTX 3060 6GB.
3. **Eliminate silent evaluation corruptions** from port collisions and stale server processes.
4. **Transition from a destructive "hard discard" sanitization model to a non-destructive "auto-repair" model**, preserving 20-30% of high-quality synthetic dialogues.
5. **Implement an offline, fully local Gap Detector** that reads physical Markdown primers to diagnose knowledge coverage failures.

---

## Prioritized Upgrade Matrix

| Task | Component | Upgrade Description | Priority | Target File | Impact |
|------|-----------|---------------------|----------|-------------|--------|
| **1.1** | Quality Gate | Refactor sequential `@pytest.mark.parametrize` to use concurrent `ThreadPoolExecutor` (max 4 workers). | **HIGH** | `test_dataset_generation_quality.py` | 4x faster quality gating |
| **1.2** | SFT Training | Configure `bnb_4bit_use_double_quant=True` inside BitsAndBytes model-loading logic. | **HIGH** | `train.py` | +0.5 GB VRAM headroom |
| **1.3** | Evaluation | Implement pre-flight dynamic free port checking and binding sequencer inside `LlamaServer.start()`. | **HIGH** | `evaluate.py` | Eliminates silent port conflicts |
| **2.1** | Sanitization | Implement soft sliding-scale quality caps and skip prompt question mark checks on command verbs. | **MEDIUM**| `sanitize_dataset.py` | Preserves valid, natural dialogues |
| **2.2** | Sanitization | Implement non-destructive `trim_to_max_sentences` and structural punctuation repair helper routines. | **MEDIUM**| `sanitize_dataset.py` | Auto-fixes sentence budgets in-place |
| **2.3** | Sanitization | Wrap AI disclaimers in `\b` boundaries; support `--artifact-check repair` filtering mode. | **MEDIUM**| `sanitize_dataset.py` | Avoids false positives on safe terms |
| **2.4** | Quality Gate | Incorporate G-Eval judge prompt optimizations (brief summaries, passing/failing few-shot coaching). | **MEDIUM**| `dataset_eval.py` | Minimizes judge hallucinations |
| **3.1** | SFT Training | Implement causal attention masking on packed collators to prevent cross-example leakages. | **MEDIUM**| `train.py` | Guarantees training data isolation |
| **3.2** | SFT Training | Add SFT parameter configuration support for `neftune_noise_alpha` embedding noise injection. | **MEDIUM**| `train.py` | Prevents overfitting on small datasets |
| **4.1** | Feedback Loop | Replace stubbed Step 3 with `LocalGapDetector` checking spec aliases against the physical Markdown primer. | **MEDIUM**| `feedback_loop.py` | Localizes knowledge-gap diagnosis |
| **4.2** | Evaluation | Refactor `LlamaServer.query()` to use SSE streaming with trailing bigram and phrase regex checks. | **LOW**   | `evaluate.py` | Halts repeating loops in real-time |
| **4.3** | Evaluation | Create `scripts/evaluation/benchmark_judge.py` to measure judge model slot consistency. | **LOW**   | New file    | Controls judge model bias |

---

## Technical Backlog & Implementation Guidelines

### High-Priority Milestones (Phase 1)

#### 1. DeepEval Concurrent Threading
Refactor the parameterization in `test_dataset_generation_quality.py`. Instead of running test cases sequentially, utilize a single test function that dispatches `assert_test()` calls concurrently across a thread pool:
```python
def test_generated_dataset_quality():
    import concurrent.futures
    errors = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(assert_test, case, DATASET_QUALITY_METRICS): case for case in TEST_CASES}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                errors.append(e)
                
    if errors:
        raise AssertionError(f"{len(errors)} cases failed quality metrics.")
```

#### 2. BitsAndBytes Double Quantization
Locate `get_model_and_tokenizer` in `train.py`. Deep inside the `BitsAndBytesConfig` definition, explicitly set:
```python
bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,  # Saves ~0.4 GB of VRAM
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16,
)
```

#### 3. Dynamic Free Port Allocation
Implement socket pre-flight checks inside `LlamaServer` start routine:
```python
def find_free_port(start_port: int, host: str = "127.0.0.1", max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port available")
```

---

### Medium-Priority Milestones (Phase 2 & 3)

#### 4. Non-Destructive Sanitizer Repairs
Refactor `sanitize_dataset.py` to support `--artifact-check repair`. If a sentence contains an AI disclaimer, slice and filter out *only that sentence*, joining the rest back together:
```python
def repair_and_filter_artifacts(content: str) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', content.strip())
    repaired = [s for s in sentences if not contains_ai_artifact(s)]
    return " ".join(repaired)
```
Add sentence-trimming and punctuation repairs, and map warnings to `meta_warnings` to prevent hard discards.

#### 5. Local Gap Coverage Analyzer
Implement the `LocalGapDetector` class in `feedback_loop.py`. If a concept has a low win rate, search for its name and aliases (extracted from the specification JSON) inside the physical reference document `data/npcs/reference_docs/{npc_key}_primer.md`:
* **Knowledge Gap**: Term matches in the primer == `0`. (Action: Expand source document).
* **Training Density Gap**: Term matches in primer > 0, but cleaned training example count < `8`. (Action: Regenerate synthetic SFT data).

---

### Low-Priority Milestones (Phase 4)

#### 6. Streaming Repetition Protection
Replace the blocking POST call in `LlamaServer.query()` with a streaming event-source consumer. Maintain a trailing window of generated tokens, calculating the Type-Token Ratio (TTR) of bigrams. If TTR falls below `0.45` on sequences longer than 15 words, force-terminate the stream by closing the response socket.

---

## Strategic Rollout

We recommend executing this roadmap incrementally across three sequential sweeps:
1. **Sweep 1 (Robustness Quick-Wins)**: Complete tasks 1.1, 1.2, and 1.3 to speed up the loop and lock down VRAM stability.
2. **Sweep 2 (Sanitization & Local Gaps)**: Complete tasks 2.1, 2.2, 2.3, and 4.1 to reduce discard noise and localize gap classification.
3. **Sweep 3 (Stability & Guarding)**: Complete tasks 3.1, 3.2, and 4.2 to seal token leaks and add real-time loop protection.
