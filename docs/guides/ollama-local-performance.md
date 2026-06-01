# Local Ollama Performance Notes

This document captures the operating goals for Ollama on this machine before asking for remote high-capacity instances.

## Goals
- Keep local generation usable for dataset creation.
- Keep local DeepEval judging reliable.
- Use measured numbers, not guesses, when discussing performance.
- Show investors clear evidence of current limits and bottlenecks.

## What to measure
- Loaded model name
- Number of loaded models
- GPU VRAM usage before, during, and after a run
- Latency per request
- Tokens per second
- Timeout and failure rate
- Concurrency behavior
- Judge throughput for DeepEval

## Recommended checks
- `ollama ps`
- `nvidia-smi`
- `curl http://localhost:11434/api/tags`

## Local tuning priorities
- Prefer a single loaded model when VRAM is limited.
- Reduce concurrency before increasing context or batch size.
- Use the smallest acceptable judge model for DeepEval.
- Benchmark any change before treating it as an improvement.

## Decision rule
If local measurements are unstable or too slow, optimize locally first. Only after benchmark evidence should remote GPUs be proposed as the next step.
