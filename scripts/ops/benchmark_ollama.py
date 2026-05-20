#!/usr/bin/env python3
"""Benchmark local Ollama performance on this machine.

The script captures:
- running models from `ollama ps`
- available tags from the local Ollama server
- GPU VRAM usage from `nvidia-smi`
- one or more timed chat requests

It prints a JSON report to stdout and optionally writes the same payload to a file.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class ChatBenchmarkResult:
    model: str
    prompt: str
    latency_ms: float | None
    eval_count: int | None
    eval_duration_ms: float | None
    prompt_eval_count: int | None
    prompt_eval_duration_ms: float | None
    tokens_per_second: float | None
    error: str | None = None


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as exc:  # pragma: no cover - best-effort diagnostics
        return 1, "", str(exc)


def parse_ollama_ps(output: str) -> list[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    if lines[0].lower().startswith("name"):
        lines = lines[1:]
    models: list[str] = []
    for line in lines:
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def get_running_models() -> dict[str, Any]:
    code, stdout, stderr = run_cmd(["ollama", "ps"], timeout=20)
    return {
        "returncode": code,
        "stdout": stdout,
        "stderr": stderr,
        "models": parse_ollama_ps(stdout) if code == 0 else [],
    }


def get_api_tags(host: str) -> dict[str, Any]:
    url = host.rstrip("/") + "/api/tags"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return {"ok": True, "url": url, "data": resp.json()}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)}


def get_gpu_usage() -> dict[str, Any]:
    query = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    code, stdout, stderr = run_cmd(query, timeout=20)
    usage: list[dict[str, Any]] = []
    if code == 0 and stdout:
        for line in stdout.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) >= 5:
                usage.append(
                    {
                        "index": parts[0],
                        "name": parts[1],
                        "memory_used_mb": int(float(parts[2])),
                        "memory_total_mb": int(float(parts[3])),
                        "gpu_utilization_pct": int(float(parts[4])),
                    }
                )
    return {"returncode": code, "stdout": stdout, "stderr": stderr, "gpus": usage}


def benchmark_chat(host: str, model: str, prompt: str, system_prompt: str | None = None) -> ChatBenchmarkResult:
    url = host.rstrip("/") + "/api/chat"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.0,
            "num_predict": 64,
        },
    }

    started = time.perf_counter()
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        data = resp.json()
        eval_count = data.get("eval_count")
        eval_duration_ns = data.get("eval_duration")
        prompt_eval_count = data.get("prompt_eval_count")
        prompt_eval_duration_ns = data.get("prompt_eval_duration")
        tokens_per_second = None
        if isinstance(eval_count, (int, float)) and isinstance(eval_duration_ns, (int, float)) and eval_duration_ns > 0:
            tokens_per_second = float(eval_count) / (float(eval_duration_ns) / 1_000_000_000.0)
        return ChatBenchmarkResult(
            model=model,
            prompt=prompt,
            latency_ms=round(elapsed_ms, 2),
            eval_count=int(eval_count) if isinstance(eval_count, (int, float)) else None,
            eval_duration_ms=round(float(eval_duration_ns) / 1_000_000.0, 2) if isinstance(eval_duration_ns, (int, float)) else None,
            prompt_eval_count=int(prompt_eval_count) if isinstance(prompt_eval_count, (int, float)) else None,
            prompt_eval_duration_ms=round(float(prompt_eval_duration_ns) / 1_000_000.0, 2) if isinstance(prompt_eval_duration_ns, (int, float)) else None,
            tokens_per_second=round(tokens_per_second, 2) if tokens_per_second is not None else None,
        )
    except Exception as exc:
        return ChatBenchmarkResult(
            model=model,
            prompt=prompt,
            latency_ms=None,
            eval_count=None,
            eval_duration_ms=None,
            prompt_eval_count=None,
            prompt_eval_duration_ms=None,
            tokens_per_second=None,
            error=str(exc),
        )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    running_models = get_running_models()
    api_tags = get_api_tags(args.host)
    gpu_usage = get_gpu_usage()

    selected_model = args.model or (running_models["models"][0] if running_models["models"] else None)
    chat_results: list[dict[str, Any]] = []
    if selected_model:
        prompts = args.prompt if args.prompt else [
            "Reply in one concise sentence: what is the main idea of this benchmark?",
        ]
        for prompt in prompts:
            result = benchmark_chat(args.host, selected_model, prompt, args.system_prompt)
            chat_results.append(result.__dict__)

    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": args.host,
        "selected_model": selected_model,
        "running_models": running_models,
        "api_tags": api_tags,
        "gpu_usage": gpu_usage,
        "chat_results": chat_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark local Ollama performance")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"), help="Ollama host URL")
    parser.add_argument("--model", help="Model name to benchmark. Defaults to the first running model.")
    parser.add_argument("--prompt", action="append", help="Prompt to benchmark; may be supplied multiple times.")
    parser.add_argument("--system-prompt", help="Optional system prompt used for benchmark requests.")
    parser.add_argument("--output", help="Optional path to write the JSON report.")
    parser.add_argument("--quick", action="store_true", help="Run a single short prompt if no custom prompts are supplied.")
    args = parser.parse_args()

    if args.quick and not args.prompt:
        args.prompt = ["Reply in one short sentence about local inference benchmarking."]

    report = build_report(args)
    payload = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")

    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
