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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dataset.dataset_contracts import calculate_distribution_gaps, expected_examples_per_category, summarize_jsonl_dataset
from scripts.ops.confident_api import ConfidentAPIClient
from scripts.ops.env_loader import confident_available, ensure_confident_api_key
from scripts.ops.preflight import run_preflight
from scripts.ops.ollama_model_presets import resolve_ollama_model
from scripts.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path
from _config.workflow_context import resolve_workflow_context

DEEPEVAL_TEST = PROJECT_ROOT / "tests" / "evals" / "test_dataset_generation_quality.py"
DEFAULT_FAST_CASES_PER_CATEGORY = 1
DEFAULT_PRODUCTION_CASES_PER_CATEGORY = 5
DEFAULT_DATASET_EVAL_MODE = "fast"
DATASET_EVAL_MODES = ("fast", "release")


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
    latest = PROJECT_ROOT / ".deepeval" / ".latest_run_full.json"
    if not latest.exists():
        latest = PROJECT_ROOT / ".deepeval" / ".latest_test_run.json"
    if not latest.exists():
        raise SystemExit("Error: DeepEval did not write .deepeval/.latest_run_full.json")
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


def summarize_deepeval_result(result: dict, *, npc_key: str, technique: str, judge_model: str, judge_provider: str = "ollama", command: list[str]) -> tuple[dict, list[dict]]:
    test_cases = (result.get("testCases") or result.get("test_cases") or []) + (
        result.get("conversationalTestCases") or result.get("conversational_test_cases") or []
    )
    total = len(test_cases)
    passed = sum(1 for case in test_cases if case.get("success") is True)
    failed = total - passed
    failures: list[dict] = []
    metric_totals: dict[str, dict[str, float]] = {}
    category_totals: dict[str, dict[str, int]] = {}
    metric_count = 0
    null_metric_count = 0
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
            metric_count += 1
            name = metric.get("name") or "unknown"
            score = metric.get("score")
            if score is None:
                null_metric_count += 1
            elif isinstance(score, (int, float)):
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
        "judge_provider": judge_provider,
        "judge_model": judge_model,
        "deepeval_identifier": requested_identifier or result_identifier,
        "deepeval_result_identifier": result_identifier,
        "command": command,
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "metric_count": metric_count,
        "null_metric_count": null_metric_count,
        "null_metric_rate": round(null_metric_count / metric_count, 4) if metric_count else 0.0,
        "status": "inconclusive" if metric_count and (null_metric_count / metric_count) > 0.5 else "ok",
        "metrics": metric_summary,
        "categories": category_summary,
        "failures_path": str(dataset_dir(npc_key, technique) / "quality_failures.json"),
    }
    return summary, failures


def _build_metric_collection() -> dict:
    """Build a metric collection matching the local evaluation metrics."""
    return {
        "name": "npc-dataset-quality",
        "include": ["answer_relevancy", "faithfulness", "hallucination"],
    }


def _convert_test_cases_for_remote(jsonl_path: Path) -> list[dict]:
    """Read a ChatML JSONL dataset and convert rows to Confident API test cases."""
    test_cases: list[dict] = []
    if not jsonl_path.exists():
        return test_cases
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            messages = row.get("messages") if isinstance(row, dict) else None
            if not isinstance(messages, list) or len(messages) < 2:
                continue
            # Extract system prompt (first message with role "system")
            system_prompt = ""
            for msg in messages:
                if msg.get("role") == "system":
                    system_prompt = msg.get("content", "")
                    break
            # Extract first user and assistant messages
            user_message = ""
            assistant_message = ""
            for msg in messages:
                role = msg.get("role", "")
                if role == "user" and not user_message:
                    user_message = msg.get("content", "")
                elif role == "assistant" and not assistant_message:
                    assistant_message = msg.get("content", "")
            if not user_message:
                continue
            metadata = row.get("metadata") or {}
            category = metadata.get("category", "")
            difficulty = metadata.get("difficulty", "")
            additional_metadata: dict[str, str] = {}
            if category:
                additional_metadata["category"] = category
            if difficulty:
                additional_metadata["difficulty"] = difficulty
            test_cases.append({
                "input": user_message,
                "actualOutput": "",
                "expectedOutput": assistant_message,
                "context": [system_prompt] if system_prompt else [],
                "additionalMetadata": additional_metadata if additional_metadata else {},
            })
    return test_cases


def load_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return load_json(path)
    except Exception as e:
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


def effective_cases_per_category(args: argparse.Namespace) -> int:
    if args.cases_per_category is not None:
        return args.cases_per_category
    if args.mode == "release":
        return DEFAULT_PRODUCTION_CASES_PER_CATEGORY
    return DEFAULT_FAST_CASES_PER_CATEGORY


def sanitizer_quality_issues(manifest: dict) -> tuple[dict, list[str]]:
    statistics = manifest.get("statistics") if isinstance(manifest, dict) else {}
    discarded = manifest.get("discarded") if isinstance(manifest, dict) else {}
    quality_scores = statistics.get("quality_scores") if isinstance(statistics, dict) else {}
    total_output = int(statistics.get("total_output", 0) or 0) if isinstance(statistics, dict) else 0
    flagged = int(quality_scores.get("flagged_for_review", 0) or 0) if isinstance(quality_scores, dict) else 0
    passed_threshold = int(quality_scores.get("passed_threshold", total_output) or 0) if isinstance(quality_scores, dict) else total_output
    discarded_total = int(discarded.get("total", 0) or 0) if isinstance(discarded, dict) else 0

    issues: list[str] = []
    if flagged > 0:
        issues.append(f"sanitizer flagged {flagged} row(s) for review")
    if total_output > 0 and passed_threshold < total_output:
        issues.append(f"sanitizer quality threshold passed {passed_threshold}/{total_output} output row(s)")

    return {
        "total_output": total_output,
        "discarded_total": discarded_total,
        "flagged_for_review": flagged,
        "passed_threshold": passed_threshold,
        "quality_scores": quality_scores if isinstance(quality_scores, dict) else {},
    }, issues


def dataset_eval_exit_code(summary: dict, deepeval_returncode: int, mode: str, *, soft_fail: bool = False) -> int:
    if soft_fail:
        return 0
    if summary.get("distribution_gaps") or summary.get("dataset_unknown_rows", 0) or summary.get("sanitizer_quality_issues"):
        return deepeval_returncode or 2
    if summary.get("status") == "inconclusive":
        return 2
    if mode == "fast":
        return 0
    return deepeval_returncode


def run_deepeval(args: argparse.Namespace, spec: dict) -> int:
    workflow = resolve_workflow_context(spec_path=Path(spec.get("__path__", args.spec)), spec=spec, technique=args.technique)
    npc_key = workflow.npc_key
    technique = workflow.technique
    clean_path = workflow.dataset_path if workflow.dataset_path.name == "train_clean.jsonl" else workflow.dataset_clean_path
    if not clean_path.exists():
        raise SystemExit(
            f"Error: {clean_path} does not exist. Run sanitize first, for example:\n"
            f"  ./ucore sanitize subjects/datasets/{npc_key}/{technique}/train.jsonl "
            f"--output subjects/datasets/{npc_key}/{technique}/train_clean.jsonl --strict-canonical"
        )

    cases_per_category = effective_cases_per_category(args)
    identifier = args.identifier or f"dataset-quality-{npc_key}-{technique}-{args.mode}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
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
    from scripts.ops.run_registry import PipelineRun, archive_quality_artifact
    from _config.log_setup import set_active_run, clear_active_run

    with PipelineRun(
        npc_key=npc_key,
        stage="dataset_eval",
        technique=technique,
        spec_path=args.spec,
        entrypoint="cli"
    ) as run:
        set_active_run(run.run_id, run.run_dir)
        output_dir = dataset_dir(npc_key, technique)
        summary_path = output_dir / "quality_summary.json"
        failures_path = output_dir / "quality_failures.json"
        report_path = output_dir / "quality_report.json"
        summary = {"passed": 0, "total": 0, "pass_rate": 0.0}
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        try:
            judge_provider = args.judge_provider
            if judge_provider == "wandb":
                resolved_judge_model = args.judge_model or "meta-llama/Llama-3.1-8B-Instruct"
            else:
                resolved_judge_model = resolve_ollama_model(preset=args.judge_preset, model=args.judge_model, role="judge")
            hook_recorder = WorkflowHookRecorder(
                args.workflow_hooks or run.hook_path,
                tool="dataset_eval",
                npc_key=npc_key,
                technique=technique,
                spec_path=args.spec,
                run_id=run.run_id,
            )
            with hook_recorder.step("deepeval_run", identifier=identifier, judge_provider=judge_provider, judge_model=resolved_judge_model, cases_per_category=cases_per_category, mode=args.mode):
                preflight = None
                if judge_provider == "ollama" and not getattr(args, 'remote_eval', False):
                    preflight = run_preflight(
                        phase="dataset_eval",
                        preset=None,
                        spec_path=args.spec,
                        technique=technique,
                        ollama_url=args.ollama_base_url,
                        auto_unload_ollama=True,
                        require_gcc=False,
                    )
                    if preflight.stopped_ollama_models:
                        print(
                            f"Stopped Ollama model(s) before DeepEval: {', '.join(preflight.stopped_ollama_models)}",
                            flush=True,
                        )
                    if preflight.warnings:
                        for warning in preflight.warnings:
                            print(f"[preflight] {warning}", flush=True)

                if args.ignore_errors:
                    cmd.append("--ignore-errors")

                if judge_provider == "ollama" and not os.getenv("OLLAMA_NUM_PARALLEL"):
                    print(
                        "[recommended] OLLAMA_NUM_PARALLEL is not set. For 5x-10x faster async evaluation, "
                        "set BEFORE starting Ollama:  export OLLAMA_NUM_PARALLEL=4",
                        "Also consider:  export OLLAMA_FLASH_ATTENTION=1  export OLLAMA_KV_CACHE_TYPE=q8_0",
                        flush=True,
                    )

                env = os.environ.copy()
                existing_pythonpath = env.get("PYTHONPATH", "")
                env["PYTHONPATH"] = (
                    f"{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}"
                    if existing_pythonpath
                    else str(PROJECT_ROOT)
                )
                # Propagate Confident AI key explicitly so the deepeval subprocess
                # can upload results even when its cwd differs from PROJECT_ROOT
                # (DeepEval 4.x auto-loads .env.local from cwd, but belt-and-suspenders).
                confident_key = os.getenv("CONFIDENT_API_KEY", "")
                env.update(
                    {
                        "DEEPEVAL_DATASET_LIVE": "1",
                        "DEEPEVAL_DATASET_NPC_KEYS": npc_key,
                        "DEEPEVAL_DATASET_TECHNIQUE": technique,
                        "DEEPEVAL_DATASET_CASES_PER_CATEGORY": str(cases_per_category),
                        "DEEPEVAL_JUDGE_PROVIDER": judge_provider,
                        "DEEPEVAL_OLLAMA_MODEL": resolved_judge_model,
                        "DEEPEVAL_OLLAMA_BASE_URL": args.ollama_base_url,
                        "DEEPEVAL_OLLAMA_TEMPERATURE": str(args.judge_temperature),
                        "DEEPEVAL_WANDB_MODEL": resolved_judge_model,
                        "DEEPEVAL_WANDB_TEMPERATURE": str(args.judge_temperature),
                        "DEEPEVAL_WANDB_ENTITY": args.wandb_inference_entity or args.wandb_entity or os.getenv("WANDB_ENTITY", ""),
                        "DEEPEVAL_WANDB_PROJECT": args.wandb_inference_project or args.wandb_project or os.getenv("WANDB_PROJECT", ""),
                        "DEEPEVAL_TELEMETRY_OPT_OUT": "1",
                        "DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE": os.getenv("DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE", "600"),
                        # Suppress browser pop-up in headless / CI runs.
                        "CONFIDENT_OPEN_BROWSER": "false",
                        **({
                            "CONFIDENT_API_KEY": confident_key,
                        } if confident_key else {}),
                    }
                )
                if args.categories:
                    env["DEEPEVAL_DATASET_CATEGORIES"] = args.categories

                # ── Confident AI Setup ────────────────────────────────────────
                confident_key_found = ensure_confident_api_key()
                if confident_key_found:
                    print("Confident AI: results will auto-upload to hosted dashboard", flush=True)
                else:
                    print(
                        "Confident AI: not configured (set CONFIDENT_API_KEY or run 'deepeval login')",
                        flush=True,
                    )
                if args.confident and not confident_key_found:
                    raise SystemExit(
                        "Error: --confident was passed but CONFIDENT_API_KEY is not set.\n"
                        "Set the environment variable or run 'deepeval login' first."
                    )

                # ── Remote Eval Path (Confident AI) ──────────────────────────
                if args.remote_eval:
                    if not args.confident:
                        print("Error: --remote-eval requires --confident (Confident API key).", flush=True)
                        sys.exit(1)

                    print("\n[Remote Eval] Evaluating on Confident AI infrastructure...", flush=True)
                    client = ConfidentAPIClient()
                    metric_collection = _build_metric_collection()
                    test_cases = _convert_test_cases_for_remote(clean_path)

                    result = client.evaluate(test_cases, metric_collection, identifier=identifier)
                    test_run_id = result.get("data", {}).get("testRunId", "")
                    print(f"Remote evaluation submitted. Test Run ID: {test_run_id}", flush=True)
                    print(f"View results: https://app.confident-ai.com/test-runs/{test_run_id}", flush=True)

                    # Build summary matching local shape for downstream code
                    summary = {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "npc_key": npc_key,
                        "technique": technique,
                        "judge_provider": "confident",
                        "judge_model": "hosted",
                        "deepeval_identifier": identifier,
                        "quality_gate_mode": args.mode,
                        "cases_per_category": cases_per_category,
                        "total": len(test_cases),
                        "passed": 0,
                        "failed": 0,
                        "pass_rate": 0.0,
                        "status": "ok",
                        "remote_eval": True,
                        "test_run_id": test_run_id,
                        "confident_url": f"https://app.confident-ai.com/test-runs/{test_run_id}",
                        "metric_count": 0,
                        "null_metric_count": 0,
                        "null_metric_rate": 0.0,
                        "metrics": {},
                        "categories": {},
                    }
                    # Enrich with dataset info (same as local path)
                    dataset_summary = summarize_jsonl_dataset(clean_path)
                    expected_distribution = expected_examples_per_category(spec)
                    distribution_gaps = calculate_distribution_gaps(expected_distribution, dataset_summary.get("by_category", {}))
                    manifest = load_optional_json(output_dir / "train_manifest.json") or {}
                    sanitizer_summary, sanitizer_issues = sanitizer_quality_issues(manifest)
                    summary.update({
                        "dataset_summary": dataset_summary,
                        "expected_distribution": expected_distribution,
                        "distribution_gaps": distribution_gaps,
                        "dataset_total_rows": dataset_summary.get("total", 0),
                        "dataset_unknown_rows": dataset_summary.get("unknown_rows", 0),
                        "sanitizer": sanitizer_summary,
                        "sanitizer_quality_issues": sanitizer_issues,
                    })
                    if distribution_gaps or dataset_summary.get("unknown_rows", 0) or sanitizer_issues:
                        summary["status"] = "structural_failure" if summary.get("status") == "ok" else summary.get("status")

                    failures: list[dict] = []
                    combined_report = build_combined_quality_report(
                        spec=spec,
                        technique=technique,
                        clean_path=clean_path,
                        manifest_path=output_dir / "train_manifest.json",
                        summary=summary,
                        failures=failures,
                    )
                    output_dir = dataset_dir(npc_key, technique)
                    summary_path = Path(args.output) if args.output else output_dir / "quality_summary.json"
                    failures_path = output_dir / "quality_failures.json"
                    report_path = output_dir / "quality_report.json"
                    write_json(summary_path, summary)
                    write_json(failures_path, failures)
                    write_json(report_path, combined_report)

                    archive_quality_artifact(summary_path, run.run_id)
                    archive_quality_artifact(failures_path, run.run_id)
                    archive_quality_artifact(report_path, run.run_id)
                else:
                    # ── Local Eval Path ──────────────────────────────────────────
                    print(f"Running: {' '.join(cmd)}", flush=True)
                    completed = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)

                    result = latest_deepeval_result()
                    summary, failures = summarize_deepeval_result(
                        result,
                        npc_key=npc_key,
                        technique=technique,
                        judge_model=resolved_judge_model,
                        judge_provider=judge_provider,
                        command=cmd,
                    )
                    if summary.get("deepeval_result_identifier") and summary.get("deepeval_result_identifier") != identifier:
                        summary["status"] = "inconclusive"
                        summary["result_identifier_mismatch"] = {
                            "expected": identifier,
                            "actual": summary.get("deepeval_result_identifier"),
                        }
                    dataset_summary = summarize_jsonl_dataset(clean_path)
                    expected_distribution = expected_examples_per_category(spec)
                    distribution_gaps = calculate_distribution_gaps(expected_distribution, dataset_summary.get("by_category", {}))
                    manifest = load_optional_json(output_dir / "train_manifest.json") or {}
                    sanitizer_summary, sanitizer_issues = sanitizer_quality_issues(manifest)
                    summary.update(
                        {
                            "quality_gate_mode": args.mode,
                            "cases_per_category": cases_per_category,
                            "dataset_summary": dataset_summary,
                            "expected_distribution": expected_distribution,
                            "distribution_gaps": distribution_gaps,
                            "dataset_total_rows": dataset_summary.get("total", 0),
                            "dataset_unknown_rows": dataset_summary.get("unknown_rows", 0),
                            "sanitizer": sanitizer_summary,
                            "sanitizer_quality_issues": sanitizer_issues,
                        }
                    )
                    if distribution_gaps or dataset_summary.get("unknown_rows", 0) or sanitizer_issues:
                        summary["status"] = "structural_failure" if summary.get("status") == "ok" else summary.get("status")
                    output_dir = dataset_dir(npc_key, technique)
                    summary_path = Path(args.output) if args.output else output_dir / "quality_summary.json"
                    failures_path = output_dir / "quality_failures.json"
                    report_path = output_dir / "quality_report.json"
                    combined_report = build_combined_quality_report(
                        spec=spec,
                        technique=technique,
                        clean_path=clean_path,
                        manifest_path=output_dir / "train_manifest.json",
                        summary=summary,
                        failures=failures,
                    )
                    write_json(summary_path, summary)
                    write_json(failures_path, failures)
                    write_json(report_path, combined_report)

                    archive_quality_artifact(summary_path, run.run_id)
                    archive_quality_artifact(failures_path, run.run_id)
                    archive_quality_artifact(report_path, run.run_id)

                    # (Test runs are uploaded automatically to Confident AI via the deepeval CLI)

                # ── Confident AI Dashboard Link ────────────────────────────────
                if confident_available():
                    print("\U0001F4CA Confident AI dashboard: https://app.confident-ai.com/")
                    print(f"   Look for run identifier: {identifier}")

            # ── W&B Dataset Quality Gate Tracking ──────────────────────────────
            if args.wandb:
                try:
                    import wandb
                    wandb_run = wandb.init(
                        project=args.wandb_project or "unsloth-core",
                        entity=args.wandb_entity,
                        group=os.environ.get("WANDB_GROUP"),
                        job_type="dataset-quality-gate",
                        config={
                            "npc_key": npc_key,
                            "technique": technique,
                            "judge_provider": judge_provider,
                            "judge_model": resolved_judge_model,
                            "cases_per_category": cases_per_category,
                            "quality_gate_mode": args.mode,
                            "total": summary["total"],
                            "passed": summary["passed"],
                            "failed": summary["failed"],
                            "pass_rate": summary["pass_rate"],
                        },
                        name=f"dataset-quality-{npc_key}-{technique}",
                        tags=["dataset-quality", npc_key, technique],
                    )
                    if wandb_run and getattr(wandb_run, "url", None):
                        print(f"  [wandb] Run URL: {wandb_run.url}")

                    # Log summary metrics
                    wandb.log({
                        "quality/pass_rate": summary["pass_rate"],
                        "quality/total": summary["total"],
                        "quality/passed": summary["passed"],
                        "quality/failed": summary["failed"],
                        "quality/null_metric_count": summary.get("null_metric_count", 0),
                        "quality/null_metric_rate": summary.get("null_metric_rate", 0),
                        "quality/total_rows": summary.get("dataset_total_rows", 0),
                        "quality/unknown_rows": summary.get("dataset_unknown_rows", 0),
                    })

                    # Log per-category metrics
                    for cat, cat_stats in summary.get("categories", {}).items():
                        cat_pass_rate = cat_stats.get("pass_rate", 0) or 0
                        wandb.log({
                            f"quality/category/{cat}/pass_rate": cat_pass_rate,
                            f"quality/category/{cat}/total": cat_stats.get("total", 0),
                            f"quality/category/{cat}/passed": cat_stats.get("passed", 0),
                            f"quality/category/{cat}/failed": cat_stats.get("total", 0) - cat_stats.get("passed", 0),
                        })

                    # Log quality_summary.json as artifact
                    if summary_path.exists():
                        summary_artifact = wandb.Artifact(
                            f"quality-summary-{npc_key}-{technique}",
                            type="quality-report",
                            description=f"DeepEval quality summary for {npc_key} ({technique})",
                            metadata={
                                "npc_key": npc_key,
                                "technique": technique,
                                "pass_rate": summary["pass_rate"],
                                "total": summary["total"],
                            }
                        )
                        summary_artifact.add_file(str(summary_path))
                        wandb.log_artifact(summary_artifact)

                    # Log quality_failures.json as artifact
                    if failures_path.exists():
                        failures_artifact = wandb.Artifact(
                            f"quality-failures-{npc_key}-{technique}",
                            type="quality-failures",
                            description=f"DeepEval quality failures for {npc_key} ({technique})",
                            metadata={
                                "npc_key": npc_key,
                                "technique": technique,
                                "failure_count": len(failures),
                            }
                        )
                        failures_artifact.add_file(str(failures_path))
                        wandb.log_artifact(failures_artifact)

                    wandb.finish()
                except Exception as e:
                    print("  [wandb] W&B logging failed (non-fatal)")

            print()
            print(f"DeepEval dataset quality ({args.mode}): {summary['passed']}/{summary['total']} passed ({summary['pass_rate']:.0%})")
            if summary.get("status") == "inconclusive":
                print(
                    f"DeepEval status: INCONCLUSIVE ({summary['null_metric_count']}/{summary['metric_count']} metric scores were null)",
                    flush=True,
                )
            if args.mode == "fast" and summary.get("failed", 0):
                print(
                    "Fast gate note: sampled DeepEval failures are diagnostic only; structural and sanitizer failures still block.",
                    flush=True,
                )
            print(f"Summary:  {summary_path}")
            print(f"Failures: {failures_path}")
            print(f"Report:   {report_path}")

            # ── Record pipeline manifest stage ─────────────────────────────────
            try:
                from scripts.ops.pipeline_manifest import record_pipeline_stage
                # Set env vars for manifest if not already set
                os.environ.setdefault("NPC_KEY", npc_key)
                os.environ.setdefault("TECHNIQUE", technique)
                # Gather artifacts
                manifest_artifacts = {
                    "quality_summary": str(summary_path),
                    "quality_failures": str(failures_path),
                    "quality_report": str(report_path),
                }
                manifest_metadata = {
                    "deepeval_identifier": identifier,
                    "status": summary.get("status", "unknown"),
                    "pass_rate": summary.get("pass_rate"),
                    "total": summary.get("total"),
                    "passed": summary.get("passed"),
                }
                # Add confident URL if available from .latest_test_run.json
                try:
                    latest_run = PROJECT_ROOT / ".deepeval" / ".latest_test_run.json"
                    if latest_run.exists():
                        import json as _json
                        lr = _json.loads(latest_run.read_text())
                        if "testRunLink" in lr:
                            manifest_metadata["confident_url"] = lr["testRunLink"]
                except Exception:
                    pass
                record_pipeline_stage("dataset_eval", artifacts=manifest_artifacts, metadata=manifest_metadata)
                from scripts.ops.artifact_registry import record_stage_artifacts_best_effort
                record_stage_artifacts_best_effort(
                    run.run_id,
                    npc_key,
                    "dataset_eval",
                    manifest_artifacts,
                    technique=technique,
                    metadata=manifest_metadata,
                )
            except Exception:
                pass  # manifest is optional, never block pipeline

        finally:
            run.set_artifacts(summary_path=str(summary_path), failures_path=str(failures_path), report_path=str(report_path))
            run.set_metrics(passed=summary['passed'], total=summary['total'], pass_rate=summary['pass_rate'])
            clear_active_run()

    return dataset_eval_exit_code(summary, completed.returncode, args.mode, soft_fail=args.soft_fail)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local DeepEval checks on a generated dataset")
    parser.add_argument("spec", help="Path to subject spec JSON")
    parser.add_argument("--technique", default=None, choices=["docs", "ollama", "template", "openai", "anthropic"])
    parser.add_argument(
        "--judge-provider",
        default="ollama",
        choices=["ollama", "wandb"],
        help="Judge backend for DeepEval metrics (ollama local, wandb hosted Serverless Inference)",
    )
    parser.add_argument(
        "--judge-preset",
        default=None,
        choices=["judge-qwen25", "judge-llama31-exp", "judge-qwen35-exp", "judge-qwen3-exp"],
        help="Named Ollama judge preset (default: judge-qwen3-exp)",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Exact Ollama judge model override (wins over --judge-preset)",
    )
    parser.add_argument("--ollama-base-url", default="http://localhost:11434", help="Ollama server URL")
    parser.add_argument("--judge-temperature", type=float, default=0.0)
    parser.add_argument("--mode", default=DEFAULT_DATASET_EVAL_MODE, choices=DATASET_EVAL_MODES,
                        help="Gate mode: fast is iteration-friendly; release is strict and fails on sampled metric failures")
    parser.add_argument("--cases-per-category", type=int, default=None,
                        help="Rows sampled per category (default: 1 for fast, 5 for release)")
    parser.add_argument("--categories", help="Comma-separated category filter")
    parser.add_argument("--identifier", help="DeepEval run identifier")
    parser.add_argument("--display", default="all", choices=["all", "failing", "passing"])
    parser.add_argument("--ignore-errors", action="store_true", help="Continue when individual DeepEval metric calls error")
    parser.add_argument("--soft-fail", action="store_true", help="Write artifacts but return 0 even when metrics fail")
    parser.add_argument("--output", help="Quality summary JSON path")
    parser.add_argument("--workflow-hooks", default=None,
                        help="Path to a JSONL hook log for step tracing (default: <dataset-dir>/workflow_hooks.jsonl)")
    parser.add_argument("--push-to-confident", action="store_true",
                        help="Push the combined quality report to Confident AI as a named dataset artifact (requires CONFIDENT_API_KEY)")
    parser.add_argument("--wandb", action="store_true", help="Enable W&B logging")
    parser.add_argument("--wandb-project", default="unsloth-core", help="W&B project (default: unsloth-core)")
    parser.add_argument("--wandb-entity", default=None, help="W&B entity (default: auto-detect)")
    parser.add_argument("--wandb-inference-project", default=None, help="W&B project used for hosted judge inference (default: --wandb-project)")
    parser.add_argument("--wandb-inference-entity", default=None, help="W&B entity/team used for hosted judge inference (default: --wandb-entity)")
    parser.add_argument("--confident", action="store_true", default=False,
                        help="Require Confident AI API key (exits with error if not configured)")
    parser.add_argument("--remote-eval", action="store_true", default=False,
                        help="Evaluate on Confident AI infrastructure instead of locally. Requires --confident.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = load_spec(PROJECT_ROOT / args.spec if not Path(args.spec).is_absolute() else Path(args.spec))
    raise SystemExit(run_deepeval(args, spec))


if __name__ == "__main__":
    main()
