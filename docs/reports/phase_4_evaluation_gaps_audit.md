# Technical Audit Report: Evaluation, Llama-Server & Local Gap Detection (Phase 4)

**Author:** Build Orchestrator Agent (opencode)
**Date:** 2026-06-03
**Status:** COMPLETE (Diagnostic & Optimization Phase)

---

## Executive Summary

Phase 4 of our systematic pipeline optimization audit inspects the local evaluation harness (`evaluate.py`), llama-cpp-python server coordination, local LLM judging metrics, and the SFT feedback loop state machine (`feedback_loop.py`).

Our investigations identified critical optimizations to:
1. **Expose and fix the Stale LlamaServer Port Collision Vulnerability (Task 4.1)**: Stale or parallel processes listening on the baseline port can cause silent evaluation corruption. We resolve this with a dynamic socket binding port-hunter.
2. **Standardize Local Judge Benchmarking (Task 4.2)**: Eliminate positional slot bias and formatting variance in local judges (Qwen vs. Llama) via a dedicated meta-evaluator dataset and flipped-slot testing.
3. **Build a True Local Gap Coverage Detector (Task 4.3)**: Replace the current heuristic-only gap stub with an intelligent scanner that matches SFT dataset representation volumes against the physical Markdown reference primer.
4. **Prevent Evaluation Hangs via Real-Time Loop Interruption (Task 4.4)**: Abort degenerating, repeating token stream generations mid-inference by parsing server-sent streaming chunks against a Bigram and duplicate-phrase sliding window.

---

## 1. `LlamaServer` Port Allocation & Probing Vulnerability (Task 4.1)

### The Port Collision Threat
By default, `evaluate.py` spawns two servers sequentially or overlapping during model comparison:
* **Baseline Server**: Port `args.port` (defaults to `8888`).
* **Candidate Server**: Port `args.port + 1` (defaults to `8889`).

#### The Vulnerability
If another service or a stale background `llama-server` is *already* listening on port `8888`, the health probe (`socket.create_connection` and HTTP `GET /v1/models`) returns a successful `200` immediately. 
However, the *new* server process fails to bind and crashes silently. The parent script, seeing a positive health signal from the *old* server, proceeds under the false assumption that the new server started successfully, resulting in **corrupted evaluations** where candidate prompts are evaluated against the wrong model.

### Pre-Flight Dynamic Port Hunter
We design a pre-flight checker that dynamically identifies and allocates free ports by temporarily binding a socket, automatically incrementing sequentially if a collision is found:

```python
import socket

def find_free_port(start_port: int, host: str = "127.0.0.1", max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Could not allocate free port in range {start_port}-{start_port + max_attempts - 1}")
```

---

## 2. Local Judge Benchmarking (Task 4.2)

Local judges suffer from three specific failure modes:
1. **Positional Bias (Slot Preference)**: Voting for Response A simply because it is presented first.
2. **Tie Overuse**: Failing to make a decision over minor differences.
3. **JSON Compliance Failures**: Failing to output strictly parseable JSON.

### Meta-Evaluation Framework
We implement a local benchmarking harness (`scripts/evaluation/benchmark_judge.py`) that evaluates local models against a small human-annotated "gold consensus set". 

#### Dual-Pass Testing (Flipped Slots)
For every test case:
* **Pass 1**: Prompts the judge with `(Response_A, Response_B)`.
* **Pass 2**: Prompts the judge with `(Response_B, Response_A)`.
* A consistent judge must flip its choice (`winner: A` becomes `winner: B`). If the judge votes for the same slot (e.g. Slot A in both passes), it is flagged as possessing high positional bias.

This framework determines the optimal local judge model (comparing Qwen2.5-7B, Qwen2.5-14B, and Llama3.2-3B) with empirical accuracy, format reliability, and latency.

---

## 3. Implementing a True Local Gap Coverage Detector (Task 4.3)

In `feedback_loop.py` (lines 530-555), the gap detection logic is currently stubbed with simple string-matching heuristics. If a weak concept's reasons list contains `"win_rate"`, it labels it a density gap; if it contains `"quality"`, it labels it a knowledge gap. It never checks physical files.

### The True Gap Coverage Engine (`LocalGapDetector`)
We implement a physical coverage analyzer that checks:
1. **Knowledge Coverage**: Counts term and alias frequencies inside the physical Markdown primer (`data/npcs/reference_docs/{npc_key}_primer.md`).
2. **Dataset Representation Volume**: Parses `train_clean.jsonl` to count how many cleaned SFT examples exist for that specific concept.

#### Diagnostic Rules
* **True Knowledge Gap**: If the weak concept's keywords/aliases occur **0 times** inside the primer, the failure is due to missing source content. Recommendation: Expand the primer documentation.
* **Training Density Gap**: If the concept occurs in the primer, but has **< 8 examples** in `train_clean.jsonl`, SFT representation is insufficient. Recommendation: Generate more synthetic dialogues.
* **Model Capacity Gap**: If the concept has sufficient primer coverage and **>= 8 training examples**, SFT volume is sufficient but the model failed to acquire it. Recommendation: Upgrade training preset or lr scheduler parameters.

---

## 4. Real-Time Streaming Repetition protection (Task 4.4)

Evaluation loops can enter infinite, repetitive degeneration sequences (e.g. *"the heat, the heat, the heat..."*), consuming VRAM and running slowly. Post-inference scoring is too late to prevent this.

### Real-Time Heuristic Interruption
By configuring the `LlamaServer.query()` POST request to stream tokens (`stream: True`), we parse chunks as they arrive and evaluate a sliding-window heuristic:
1. **Bigram Repetition Ratio**: If the Type-Token Ratio (TTR) of unique bigrams drops below `0.45` on sequences longer than 15 words, a loop is occurring.
2. **Consecutive Phrase Duplication**: Uses regex `\b(\w+(?:\s+\w+){0,3})\s+\1\s+\1\b` to detect short consecutive duplicates.

If triggered, the client **aborts the TCP stream immediately**, appends an repetition error notice, and saves computing time on the server.

---

## Action Items for Pipeline Implementation

| Task | Action | Target File |
|------|--------|-------------|
| **4.1** | Add `find_free_port` and integrate into `LlamaServer.start()` pre-flight | `evaluate.py` |
| **4.2** | Build `scripts/evaluation/benchmark_judge.py` meta-evaluator | New file |
| **4.3** | Implement `LocalGapDetector` to replace heuristic stubs in step 3 | `feedback_loop.py` |
| **4.4** | Refactor `LlamaServer.query()` to use SSE streaming with sliding-window TTR loops | `evaluate.py` |
