#!/usr/bin/env python3
"""Run local DeepEval quality gates for generated NPC datasets."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.dataset_contracts import calculate_distribution_gaps, expected_examples_per_category, summarize_jsonl_dataset


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEEPEVAL_TEST = PROJECT_ROOT / "tests" / "evals" / "test_dataset_generation_quality.py"
DEFAULT_PRODUCTION_CASES_PER_CATEGORY = 5


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")


def resolve_deepeval_bin() -> str:
    venv_bin = PROJECT_ROOT / "unsloth_env" / "bin" / "deepeval"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("deepeval")
    if found:
        return found
    raise SystemExit("Error: deepeval CLI not found. Activate unsloth_env or install deepeval.")


def load_spec(spec_path: Path) -> dict:
    spec = load_json(spec_path)
    if "npc_key" not in spec:
        raise SystemExit(f"Error: missing npc_key in {spec_path}")
    spec.setdefault("__path__", str(spec_path))
    return spec


def dataset_dir(npc_key: str, technique: str) -> Path:
    return PROJECT_ROOT / "subjects" / "datasets" / npc_key / technique


def latest_deepeval_result() -> dict:
    latest = PROJECT_ROOT / ".deepeval" / ".latest_test_run.json"
    if not latest.exists():
        latest = PROJECT_ROOT / ".deepeval" / ".latest_run_full.json"
    if not latest.exists():
        raise SystemExit("Error: DeepEval did not write .deepeval/.latest_test_run.json")
    result = load_json(latest)
    return result.get("testRunData", result) if isinstance(result, dict) else result


def metric_payload(metric: dict) -> dict:
    return {
        "name": metric.get("name"),
        "score": metric.get("score"),
        "threshold": metric.get("threshold"),
        "success": metric.get("success"),
        "reason": metric.get("reason"),
        "evaluation_model": metric.get("evaluationModel"),
        "error": metric.get("error"),
    }


def summarize_deepeval_result(result: dict, *, npc_key: str, technique: str, judge_model: str, command: list[str]) -> tuple[dict, list[dict]]:
    test_cases = (result.get("testCases") or result.get("test_cases") or []) + (
        result.get("conversationalTestCases") or result.get("conversational_test_cases") or []
    )
    total = len(test_cases)
    passed = sum(1 for case in test_cases if case.get("success") is True)
    failed = total - passed
    failures: list[dict] = []
    metric_totals: dict[str, dict[str, float]] = {}
    category_totals: dict[str, dict[str, int]] = {}
    result_identifier = result.get("identifier")
    requested_identifier = None
    if "--identifier" in command:
        idx = command.index("--identifier")
        if idx + 1 < len(command):
            requested_identifier = command[idx + 1]

    for case in test_cases:
        metadata = case.get("metadata") or {}
        category = metadata.get("category") or "unknown"
        category_totals.setdefault(category, {"total": 0, "passed": 0})
        category_totals[category]["total"] += 1
        if case.get("success") is True:
            category_totals[category]["passed"] += 1

        for metric in case.get("metricsData") or case.get("metrics_data") or []:
            name = metric.get("name") or "unknown"
            score = metric.get("score")
            if isinstance(score, (int, float)):
                agg = metric_totals.setdefault(name, {"count": 0, "score_sum": 0.0, "passed": 0})
                agg["count"] += 1
                agg["score_sum"] += float(score)
                if metric.get("success") is True:
                    agg["passed"] += 1
            if metric.get("success") is not True:
                failures.append(
                    {
                        "test_name": case.get("name"),
                        "input": case.get("input"),
                        "actual_output": case.get("actualOutput") or case.get("actual_output"),
                        "metadata": metadata,
                        "metric": metric_payload(metric),
                    }
                )

    metric_summary = {
        name: {
            "count": int(values["count"]),
            "average_score": round(values["score_sum"] / values["count"], 4) if values["count"] else None,
            "pass_rate": round(values["passed"] / values["count"], 4) if values["count"] else None,
        }
        for name, values in sorted(metric_totals.items())
    }
    category_summary = {
        name: {
            "total": values["total"],
            "passed": values["passed"],
            "pass_rate": round(values["passed"] / values["total"], 4) if values["total"] else None,
        }
        for name, values in sorted(category_totals.items())
    }
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "npc_key": npc_key,
        "technique": technique,
        "judge_model": judge_model,
        "deepeval_identifier": requested_identifier or result_identifier,
        "deepeval_result_identifier": result_identifier,
        "command": command,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "metrics": metric_summary,
        "categories": category_summary,
        "failures_path": str(dataset_dir(npc_key, technique) / "quality_failures.json"),
    }
    return summary, failures


def load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except Exception:
        return None


def derive_feedback_signals(summary: dict, failures: list[dict], dataset_summary: dict, expected_distribution: dict[str, int]) -> list[dict]:
    signals: list[dict] = []
    for gap in summary.get("distribution_gaps", []) or []:
        signals.append({
            "type": "distribution_gap",
            "severity": "high" if gap.get("shortfall", 0) >= gap.get("target", 0) / 2 else "medium",
            "category": gap.get("category"),
            "target": gap.get("target", 0),
            "actual": gap.get("actual", 0),
            "shortfall": gap.get("shortfall", 0),
            "suggested_action": "regenerate_more_examples_for_category",
        })

    for category, stats in summary.get("categories", {}).items():
        pass_rate = stats.get("pass_rate")
        if pass_rate is not None and pass_rate < 0.75:
            signals.append({
                "type": "deepeval_category_weakness",
                "severity": "medium",
                "category": category,
                "pass_rate": pass_rate,
                "suggested_action": "inspect_category_failures",
            })

    by_metric_failure: dict[str, int] = {}
    for failure in failures:
        metric = failure.get("metric", {}).get("name") or "unknown"
        by_metric_failure[metric] = by_metric_failure.get(metric, 0) + 1
    for metric_name, count in sorted(by_metric_failure.items(), key=lambda item: (-item[1], item[0])):
        signals.append({
            "type": "deepeval_metric_failure",
            "severity": "medium" if count < 5 else "high",
            "metric": metric_name,
            "count": count,
            "suggested_action": "review_failed_rows_and_prompts",
        })

    if dataset_summary.get("unknown_rows", 0):
        signals.append({
            "type": "dataset_parse_noise",
            "severity": "high",
            "unknown_rows": dataset_summary.get("unknown_rows", 0),
            "suggested_action": "fix_sanitizer_or_generator_output_shape",
        })

    if not signals and summary.get("pass_rate", 0) >= 0.9 and not summary.get("distribution_gaps"):
        signals.append({
            "type": "healthy",
            "severity": "low",
            "suggested_action": "no_action_needed",
        })

    return signals


def build_combined_quality_report(
    *,
    spec: dict,
    technique: str,
    clean_path: Path,
    manifest_path: Path,
    summary: dict,
    failures: list[dict],
) -> dict:
    manifest = load_optional_json(manifest_path) or {}
    dataset_summary = summary.get("dataset_summary") or summarize_jsonl_dataset(clean_path)
    expected_distribution = summary.get("expected_distribution") or expected_examples_per_category(spec)
    distribution_gaps = summary.get("distribution_gaps") or calculate_distribution_gaps(expected_distribution, dataset_summary.get("by_category", {}))
    combined = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "npc_key": spec.get("npc_key"),
        "technique": technique,
        "spec": {
            "path": spec.get("__path__"),
            "reference_doc": spec.get("reference_doc"),
            "system_prompt": spec.get("system_prompt"),
        },
        "manifest": manifest,
        "sanitizer": {
            "manifest": manifest.get("sanitizer", {}),
            "input": manifest.get("input", {}),
            "statistics": manifest.get("statistics", {}),
            "discarded": manifest.get("discarded", {}),
        },
        "dataset": {
            "path": str(clean_path),
            "summary": dataset_summary,
            "expected_distribution": expected_distribution,
            "distribution_gaps": distribution_gaps,
        },
        "deepeval": {
            "summary": summary,
            "failures": failures,
        },
        "feedback_signals": derive_feedback_signals(summary, failures, dataset_summary, expected_distribution),
    }
    return combined


def run_deepeval(args: argparse.Namespace, spec: dict) -> int:
    npc_key = spec["npc_key"]
    clean_path = dataset_dir(npc_key, args.technique) / "train_clean.jsonl"
    if not clean_path.exists():
        raise SystemExit(
            f"Error: {clean_path} does not exist. Run sanitize first, for example:\n"
            f"  ./ucore sanitize subjects/datasets/{npc_key}/{args.technique}/train.jsonl "
            f"--output subjects/datasets/{npc_key}/{args.technique}/train_clean.jsonl --strict-canonical"
        )

    identifier = args.identifier or f"dataset-quality-{npc_key}-{args.technique}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    cmd = [
        resolve_deepeval_bin(),
        "test",
        "run",
        str(DEEPEVAL_TEST),
        "--identifier",
        identifier,
        "--display",
        args.display,
        "--skip-on-missing-params",
    ]
    if args.ignore_errors:
        cmd.append("--ignore-errors")

    if not os.getenv("OLLAMA_NUM_PARALLEL"):
        print(
            "[warn] OLLAMA_NUM_PARALLEL is not set. For 5x-10x faster async evaluation, "
            "set 'export OLLAMA_NUM_PARALLEL=4' before starting your Ollama server.",
            flush=True,
        )

    env = os.environ.copy()
    env.update(
        {
            "DEEPEVAL_DATASET_NPC_KEYS": npc_key,
            "DEEPEVAL_DATASET_TECHNIQUE": args.technique,
            "DEEPEVAL_DATASET_CASES_PER_CATEGORY": str(args.cases_per_category),
            "DEEPEVAL_OLLAMA_MODEL": args.judge_model,
            "DEEPEVAL_OLLAMA_BASE_URL": args.ollama_base_url,
            "DEEPEVAL_OLLAMA_TEMPERATURE": str(args.judge_temperature),
            "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
            "DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE": os.getenv("DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE", "600"),
        }
    )
    if args.categories:
        env["DEEPEVAL_DATASET_CATEGORIES"] = args.categories

    print(f"Running: {' '.join(cmd)}", flush=True)
    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)

    result = latest_deepeval_result()
    summary, failures = summarize_deepeval_result(
        result,
        npc_key=npc_key,
        technique=args.technique,
        judge_model=args.judge_model,
        command=cmd,
    )
    dataset_summary = summarize_jsonl_dataset(clean_path)
    expected_distribution = expected_examples_per_category(spec)
    distribution_gaps = calculate_distribution_gaps(expected_distribution, dataset_summary.get("by_category", {}))
    summary.update(
        {
            "dataset_summary": dataset_summary,
            "expected_distribution": expected_distribution,
            "distribution_gaps": distribution_gaps,
            "dataset_total_rows": dataset_summary.get("total", 0),
            "dataset_unknown_rows": dataset_summary.get("unknown_rows", 0),
        }
    )
    output_dir = dataset_dir(npc_key, args.technique)
    summary_path = Path(args.output) if args.output else output_dir / "quality_summary.json"
    failures_path = output_dir / "quality_failures.json"
    report_path = output_dir / "quality_report.json"
    combined_report = build_combined_quality_report(
        spec=spec,
        technique=args.technique,
        clean_path=clean_path,
        manifest_path=output_dir / "train_manifest.json",
        summary=summary,
        failures=failures,
    )
    write_json(summary_path, summary)
    write_json(failures_path, failures)
    write_json(report_path, combined_report)

    print()
    print(f"DeepEval dataset quality: {summary['passed']}/{summary['total']} passed ({summary['pass_rate']:.0%})")
    print(f"Summary:  {summary_path}")
    print(f"Failures: {failures_path}")
    print(f"Report:   {report_path}")

    if args.soft_fail:
        return 0
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local DeepEval checks on a generated dataset")
    parser.add_argument("spec", help="Path to subject spec JSON")
    parser.add_argument("--technique", default="template", choices=["docs", "ollama", "template", "openai", "anthropic"])
    parser.add_argument("--judge-model", default="qwen2.5:7b", help="Local Ollama judge model")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434", help="Ollama server URL")
    parser.add_argument("--judge-temperature", type=float, default=0.0)
    parser.add_argument("--cases-per-category", type=int, default=DEFAULT_PRODUCTION_CASES_PER_CATEGORY)
    parser.add_argument("--categories", help="Comma-separated category filter")
    parser.add_argument("--identifier", help="DeepEval run identifier")
    parser.add_argument("--display", default="all", choices=["all", "failing", "passing"])
    parser.add_argument("--ignore-errors", action="store_true", help="Continue when individual DeepEval metric calls error")
    parser.add_argument("--soft-fail", action="store_true", help="Write artifacts but return 0 even when metrics fail")
    parser.add_argument("--output", help="Quality summary JSON path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = load_spec(PROJECT_ROOT / args.spec if not Path(args.spec).is_absolute() else Path(args.spec))
    raise SystemExit(run_deepeval(args, spec))


if __name__ == "__main__":
    main()
