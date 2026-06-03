#!/usr/bin/env python3
from __future__ import annotations

"""Compare all local Ollama models with the same prompt suite."""

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from src.core.ops.benchmark_ollama import benchmark_chat, get_api_tags, get_running_models


@dataclass
class ModelComparisonResult:
    model: str
    prompt_results: list[dict[str, Any]]
    total_latency_ms: float | None
    avg_latency_ms: float | None
    total_tokens_per_second: float | None
    avg_tokens_per_second: float | None
    successes: int
    failures: int
    score: float


def _score_prompt(result: dict[str, Any]) -> float:
    if result.get("error"):
        return -5.0
    score = 0.0
    latency = result.get("latency_ms")
    tps = result.get("tokens_per_second")
    if isinstance(latency, (int, float)):
        score += max(0.0, 1000.0 - float(latency)) / 100.0
    if isinstance(tps, (int, float)):
        score += float(tps)
    if result.get("eval_count"):
        score += min(float(result["eval_count"]) / 10.0, 3.0)
    return score


def compare_models(host: str, models: list[str], prompts: list[str], system_prompt: str | None = None) -> list[ModelComparisonResult]:
    results: list[ModelComparisonResult] = []
    for model in models:
        prompt_results: list[dict[str, Any]] = []
        scores: list[float] = []
        for prompt in prompts:
            result = benchmark_chat(host, model, prompt, system_prompt)
            payload = asdict(result)
            prompt_results.append(payload)
            scores.append(_score_prompt(payload))
        latencies = [r["latency_ms"] for r in prompt_results if isinstance(r.get("latency_ms"), (int, float))]
        tps_values = [r["tokens_per_second"] for r in prompt_results if isinstance(r.get("tokens_per_second"), (int, float))]
        successes = sum(1 for r in prompt_results if not r.get("error"))
        failures = len(prompt_results) - successes
        results.append(
            ModelComparisonResult(
                model=model,
                prompt_results=prompt_results,
                total_latency_ms=round(sum(latencies), 2) if latencies else None,
                avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else None,
                total_tokens_per_second=round(sum(tps_values), 2) if tps_values else None,
                avg_tokens_per_second=round(sum(tps_values) / len(tps_values), 2) if tps_values else None,
                successes=successes,
                failures=failures,
                score=round(sum(scores), 2),
            )
        )
    return sorted(results, key=lambda r: r.score, reverse=True)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    running = get_running_models()
    api_tags = get_api_tags(args.host)
    models = args.model if args.model else running.get("models", [])
    if args.all_tags and api_tags.get("ok"):
        tags = api_tags.get("data", {}).get("models", [])
        models = [tag.get("name") for tag in tags if tag.get("name")]
    models = [m for m in models if m]
    if not models:
        return {"host": args.host, "models": [], "error": "no_models_found", "running_models": running, "api_tags": api_tags}
    prompts = args.prompt or [
        "Reply in one short sentence about the project's main goal.",
        "Give one practical improvement you would make to dataset quality.",
        "Summarize the answer in a grounded, direct way.",
    ]
    comparison = compare_models(args.host, models, prompts, args.system_prompt)
    return {
        "host": args.host,
        "selected_models": models,
        "prompts": prompts,
        "system_prompt": args.system_prompt,
        "running_models": running,
        "api_tags": api_tags,
        "results": [asdict(result) for result in comparison],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare all local Ollama models with a shared prompt suite")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434"), help="Ollama host URL")
    parser.add_argument("--model", action="append", help="Model to benchmark; may be supplied multiple times. Defaults to running models.")
    parser.add_argument("--all-tags", action="store_true", help="Benchmark all models listed by /api/tags instead of running models")
    parser.add_argument("--prompt", action="append", help="Prompt to benchmark; may be supplied multiple times.")
    parser.add_argument("--system-prompt", help="Optional system prompt for the benchmark suite")
    parser.add_argument("--output", help="Optional path to write the JSON report")
    args = parser.parse_args()
    report = build_report(args)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
