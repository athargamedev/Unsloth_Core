#!/usr/bin/env python3
"""PipelineBundle — build professional report bundles from pipeline outputs.

Usage (CLI):
    ./ucore report bundle --npc-key chef_assistant --target-stage evaluate

This combines the PipelineRunSpec, integration audit, stage artifacts, quality
summaries, feedback JSON, and training records into one canonical report
directory under:

    artifacts/reports/<npc_key>/<run_id>/
        index.html          — HTML dashboard (single-page, self-contained)
        summary.md          — Markdown operator summary
        pipeline_run_spec.json
        stage_status.json
        integration_health.json
        dataset_quality.json
        runtime_eval_report.json
        next_actions.json
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]


# ── Fragment collectors ──────────────────────────────────────────────


def _collect_quality_fragment(npc_key: str, technique: str, data_root: Path) -> dict[str, Any]:
    """Read dataset quality summary from the canonical path."""
    path = data_root / "data" / "datasets" / npc_key / technique / "quality_summary.json"
    if not path.exists():
        return {"available": False, "reason": "quality_summary.json not found"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = {
            "available": True,
            "status": data.get("status"),
            "pass_rate": data.get("pass_rate"),
            "total": data.get("total"),
            "passed": data.get("passed"),
            "failed": data.get("failed"),
            # is_pass: explicit field, or derived from status == "ok", or pass_rate >= 0.5
            "is_pass": data.get("is_pass")
            if data.get("is_pass") is not None
            else bool(data.get("status") == "ok" or (data.get("pass_rate") or 0) >= 0.5),
            "diagnostic_pass_rate": data.get("diagnostic_pass_rate"),
            "results": data.get("results", []),
        }
        # Also check failures
        failures_path = path.parent / "quality_failures.json"
        if failures_path.exists():
            failures = json.loads(failures_path.read_text(encoding="utf-8"))
            summary["failure_count"] = len(failures) if isinstance(failures, list) else 0
        return summary
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "reason": str(e)}


def _collect_feedback_fragment(npc_key: str, data_root: Path) -> dict[str, Any]:
    """Read runtime eval feedback JSON."""
    path = data_root / "artifacts" / "eval" / "results" / "feedback" / f"{npc_key}.json"
    if not path.exists():
        return {
            "available": False,
            "reason": "feedback JSON not found — run ./ucore evaluate first",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        win_rate = data.get("overall_win_rate")
        if win_rate is None:
            win_rate = data.get("win_rate")
        total_games = data.get("total_games")
        if total_games is None:
            total_games = data.get("total_examples")
        return {
            "available": True,
            "overall_win_rate": win_rate,
            "total_games": total_games,
            "candidate_wins": data.get("candidate_wins"),
            "baseline_wins": data.get("baseline_wins"),
            "ties": data.get("ties"),
            "weak_concepts": data.get("weak_concepts", []),
            "avg_candidate_words": data.get("avg_candidate_words"),
            "avg_baseline_words": data.get("avg_baseline_words"),
        }
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "reason": str(e)}


def _artifact_path_exists(path_value: str | None, data_root: Path) -> bool:
    """Return true only when the artifact exists on disk now.

    Registry rows can contain stale `exists=true`; the bundle must prove current
    state, not repeat old registry claims.
    """
    if not path_value:
        return False
    path = Path(path_value)
    if path.is_absolute():
        return path.exists()
    return (data_root / path).exists()


def _collect_artifact_stages(
    npc_key: str, artifact_index: Path | None, data_root: Path
) -> dict[str, Any]:
    """Collect per-stage artifact summaries from the ArtifactRegistry."""
    index_path = artifact_index or data_root / ".pipeline" / "artifacts.jsonl"
    stages: dict[str, dict[str, Any]] = {}
    if not index_path.exists():
        return {"available": False, "reason": "artifact index not found"}

    try:
        lines = index_path.read_text(encoding="utf-8").strip().split("\n")
        for line in lines:
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("npc_key") != npc_key:
                continue
            stage = entry.get("stage", "unknown")
            if stage not in stages:
                stages[stage] = {
                    "artifacts": [],
                    "latest_ts": None,
                    "run_ids": set(),
                }
            entry = dict(entry)
            entry["exists_now"] = _artifact_path_exists(entry.get("path"), data_root)
            stages[stage]["artifacts"].append(entry)
            stages[stage]["run_ids"].add(entry.get("run_id", "?"))
            ts = entry.get("ts")
            if ts and (stages[stage]["latest_ts"] is None or ts > stages[stage]["latest_ts"]):
                stages[stage]["latest_ts"] = ts

        # Aggregate counts from current filesystem state.
        for s in stages.values():
            s["run_ids"] = sorted(s["run_ids"])
            existing = [a for a in s["artifacts"] if a.get("exists_now")]
            s["artifact_count"] = len(s["artifacts"])
            s["available_artifacts"] = len(existing)
            s["total_size_bytes"] = sum(a.get("size_bytes", 0) for a in existing)

        return {
            "available": bool(stages),
            "stages": {
                k: {kk: vv for kk, vv in v.items() if kk != "artifacts"} for k, v in stages.items()
            },
            "stage_list": sorted(
                k for k, v in stages.items() if v.get("available_artifacts", 0) > 0
            ),
            "total_stages": len(stages),
            "all_artifacts_present": all(
                s["artifact_count"] == s["available_artifacts"] for s in stages.values()
            ),
        }
    except (json.JSONDecodeError, OSError) as e:
        return {"available": False, "reason": str(e)}


def _collect_raw_stage_fragments(
    npc_key: str,
    technique: str,
    data_root: Path,
    artifact_index: Path | None = None,
    run_index: Path | None = None,
) -> dict[str, Any]:
    """Collect stage-specific raw data from disk for fragment files."""
    fragments: dict[str, Any] = {}

    # Dataset quality fragment
    quality = _collect_quality_fragment(npc_key, technique, data_root)
    fragments["dataset_quality"] = quality

    # Runtime eval fragment
    feedback = _collect_feedback_fragment(npc_key, data_root)
    fragments["runtime_eval"] = feedback

    # Density report (from quality data)
    density: dict[str, Any] = {"available": False, "reason": "Not computed"}
    if quality.get("available"):
        results = quality.get("results", [])
        density = {
            "available": True,
            "categories_checked": len(results),
            "categories": [r.get("category") for r in results],
        }
    fragments["density"] = density

    # Grounding report
    fragments["grounding"] = {
        "available": False,
        "reason": "Grounding verifier not run in bundle mode",
    }

    # Training report
    training = _collect_training_fragment(
        npc_key,
        data_root,
        artifact_index=artifact_index,
        run_index=run_index,
    )
    fragments["training"] = training

    return fragments


def _collect_training_fragment(
    npc_key: str,
    data_root: Path,
    artifact_index: Path | None = None,
    run_index: Path | None = None,
) -> dict[str, Any]:
    """Collect training run data from registries and artifact lineage."""
    runs = []

    # Primary current evidence: ArtifactRegistry train adapter checkpoints.
    artifact_path = artifact_index or data_root / ".pipeline" / "artifacts.jsonl"
    if artifact_path.exists():
        try:
            for line in artifact_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("npc_key") != npc_key or entry.get("stage") != "train":
                    continue
                if not _artifact_path_exists(entry.get("path"), data_root):
                    continue
                meta = entry.get("metadata") or {}
                runs.append(
                    {
                        "run_id": entry.get("run_id"),
                        "loss": meta.get("training_loss"),
                        "path": entry.get("path"),
                        "artifact_type": entry.get("artifact_type"),
                        "status": "completed",
                        "source": "artifact_registry",
                    }
                )
        except (json.JSONDecodeError, OSError) as e:
            return {"available": False, "reason": str(e)}

    # Secondary: run registry / experiment registry if present.
    run_indexes = (
        [run_index]
        if run_index
        else [
            data_root / ".pipeline" / "runs.jsonl",
            data_root / ".pipeline" / "experiments.jsonl",
        ]
    )
    for run_index_path in [p for p in run_indexes if p is not None]:
        if not run_index_path.exists():
            continue
        try:
            for line in run_index_path.read_text(encoding="utf-8").strip().split("\n"):
                if not line.strip():
                    continue
                entry = json.loads(line)
                if entry.get("npc_key") != npc_key:
                    continue
                if entry.get("stage") == "train" or "loss" in entry:
                    runs.append(
                        {
                            "run_id": entry.get("run_id"),
                            "loss": entry.get("loss"),
                            "train_samples": entry.get("train_samples"),
                            "export_gguf": entry.get("export_gguf"),
                            "status": entry.get("status"),
                            "preset": entry.get("preset"),
                            "source": run_index_path.name,
                        }
                    )
        except (json.JSONDecodeError, OSError):
            continue

    # Deduplicate while preserving order.
    seen = set()
    unique = []
    for run in runs:
        key = (run.get("run_id"), run.get("source"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(run)

    return {
        "available": bool(unique),
        "runs": unique,
        "total_runs": len(unique),
    }


# ── Summary builder ──────────────────────────────────────────────────


def _build_summary_md(
    npc_key: str,
    profile: str,
    target_stage: str,
    run_spec: dict[str, Any],
    integration: dict[str, Any],
    stage_fragments: dict[str, Any],
    artifact_stages: dict[str, Any],
    spec_ok: bool | None,
) -> str:
    """Write a professional pipeline report in markdown."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    # Determine stage-by-stage status
    quality = stage_fragments.get("dataset_quality", {})
    feedback = stage_fragments.get("runtime_eval", {})
    training = stage_fragments.get("training", {})
    artifact_info = artifact_stages

    quality_pass = quality.get("is_pass", False) if quality.get("available") else None
    feedback_pass = None
    if feedback.get("available"):
        wr = feedback.get("overall_win_rate")
        if wr is not None:
            feedback_pass = wr >= 0.5

    integration_ok = integration.get("ok", False)
    training_count = training.get("total_runs", 0) if training.get("available") else 0
    stages_found = artifact_info.get("stage_list", []) if artifact_info.get("available") else []

    lines = [
        f"# Pipeline Report: {npc_key}",
        "",
        f"**Profile:** {profile}  ",
        f"**Target Stage:** {target_stage}  ",
        f"**Generated:** {now}  ",
        "",
        "---",
        "",
        "## Executive Summary",
        "",
        f"This report evaluates the {npc_key} training pipeline readiness for",
        "parameter comparison experiments.",
        "",
    ]

    # Spec / source readiness
    spec_status = "✅ Pass" if spec_ok else ("❌ Fail" if spec_ok is False else "⚠ Not verified")
    lines.append(f"**Spec Generation-Readiness:** {spec_status}")

    # Quality gate
    if quality_pass is not None:
        q_text = (
            f"✅ Pass ({quality.get('passed', '?')}/{quality.get('total', '?')})"
            if quality_pass
            else f"❌ Fail ({quality.get('passed', '?')}/{quality.get('total', '?')})"
        )
        lines.append(f"**Dataset Quality Gate:** {q_text}")
    if quality.get("pass_rate") is not None:
        lines.append(f"  - Pass rate: {quality['pass_rate']:.0%}  ")

    # Training
    if training_count > 0:
        latest = training.get("runs", [{}])[-1]
        loss = latest.get("loss", "?")
        lines.append(f"**Training Runs:** {training_count} completed  ")
        lines.append(f"  - Latest loss: {loss}  ")
    else:
        lines.append("**Training Runs:** None (or not yet registered)  ")

    # Runtime eval
    if feedback.get("available"):
        wr_text = (
            f"✅ Win rate {feedback['overall_win_rate']:.0%}"
            if feedback_pass
            else f"❌ Win rate {feedback['overall_win_rate']:.0%}"
        )
        lines.append(f"**Runtime Eval:** {wr_text}")
        lines.append(f"  - Games: {feedback.get('total_games', '?')}  ")
        weak = feedback.get("weak_concepts", [])
        if weak:
            lines.append(f"  - Weak concepts: {', '.join(weak)}  ")
    else:
        lines.append("**Runtime Eval:** Not yet run  ")

    # Integration health
    lines.append(f"**Integration Health:** {'✅ All green' if integration_ok else '⚠ Blockers'}  ")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Stage Status",
            "",
            "| Stage | Artifacts | Status |",
            "|-------|-----------|--------|",
        ]
    )
    for stage in ["generate", "sanitize", "dataset_eval", "train", "export", "evaluate"]:
        if stage in stages_found:
            sdata = artifact_info.get("stages", {}).get(stage, {})
            count = sdata.get("available_artifacts", "?")
            lines.append(f"| {stage} | {count} | ✅ |")
        else:
            lines.append(f"| {stage} | - | ⏳ Not run |")

    lines.extend(
        [
            "",
            "## Integration Details",
            "",
        ]
    )
    for name, status in (integration.get("integrations") or {}).items():
        package = status.get("package_version") or "missing"
        cred = "✅" if status.get("credential_present") else "❌"
        req = "required" if status.get("required") else "optional"
        lines.append(f"- **{name}**: v{package} {cred} ({req})")

    lines.extend(
        [
            "",
            "## Ready for Parameter Comparison?",
            "",
        ]
    )

    ready = True
    reasons = []
    if quality_pass is None or not quality_pass:
        ready = False
        if quality_pass is None:
            reasons.append("- Dataset quality gate not yet run (`./ucore dataset-eval`)")
        else:
            reasons.append("- Dataset quality gate failing — repair required before comparison")

    if training_count == 0:
        ready = False
        reasons.append("- No training runs completed (`./ucore train`)")

    if feedback_pass is None:
        ready = False
        reasons.append("- No runtime evaluation results (`./ucore evaluate`)")
    elif feedback_pass is False:
        ready = False
        reasons.append(
            "- Runtime eval below promotion/comparison threshold — repair before parameter comparison"
        )

    if ready:
        lines.append("✅ **Yes.** The pipeline is producing measurable results with clear")
        lines.append("win/loss records, making it ready for comparison experiments.")
        lines.append("")
        lines.append("Recommended next: vary training parameters (preset, LoRA rank, learning")
        lines.append("rate, batch size) and compare against the baseline using `./ucore evaluate`.")
    else:
        lines.append("⚠ **Not yet.** The following gaps remain:")
        lines.extend(reasons)
        lines.append("")
        lines.append("After resolving, re-run this report to confirm readiness.")

    return "\n".join(lines)


# ── HTML builder ─────────────────────────────────────────────────────


def _build_index_html(
    npc_key: str,
    profile: str,
    target_stage: str,
    summary_md: str,
    run_spec: dict[str, Any],
    integration: dict[str, Any],
    stage_fragments: dict[str, Any],
) -> str:
    """Render a self-contained HTML report dashboard."""
    quality = stage_fragments.get("dataset_quality", {})
    feedback = stage_fragments.get("runtime_eval", {})
    training = stage_fragments.get("training", {})

    quality_pass = quality.get("is_pass", "N/A") if quality.get("available") else "Not run"
    wr = feedback.get("overall_win_rate", "N/A") if feedback.get("available") else "Not run"
    runs_count = training.get("total_runs", 0) if training.get("available") else 0
    int_ok = integration.get("ok", False)

    def esc(value: Any) -> str:
        return html_escape(str(value), quote=True)

    # Convert markdown-style summary to simple escaped HTML lines.
    html_lines = []
    for line in summary_md.split("\n"):
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            html_lines.append(f"<h2>{esc(line[3:])}</h2>")
        elif line.startswith("---"):
            html_lines.append("<hr>")
        elif line.startswith("**"):
            html_lines.append(f"<p>{esc(line)}</p>")
        elif line.startswith("|"):
            if "-----" in line:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if cells and "Stage" in cells:
                html_lines.append(
                    "<table><tr>" + "".join(f"<th>{esc(c)}</th>" for c in cells) + "</tr>"
                )
            elif cells:
                html_lines.append("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in cells) + "</tr>")
                if "evaluate" in line:
                    html_lines.append("</table>")
        elif line.strip():
            html_lines.append(f"<p>{esc(line)}</p>")

    body = "\n".join(html_lines)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pipeline Report: {esc(npc_key)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem; background: #0d1117; color: #c9d1d9; }}
  h1 {{ color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 0.5rem; }}
  h2 {{ color: #f0f6fc; margin-top: 2rem; }}
  hr {{ border: none; border-top: 1px solid #30363d; }}
  p {{ line-height: 1.6; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #30363d; padding: 0.5rem 1rem; text-align: left; }}
  th {{ background: #161b22; }}
  .pass {{ color: #3fb950; }}
  .fail {{ color: #f85149; }}
  .warn {{ color: #d29922; }}
  .meta {{ color: #8b949e; font-size: 0.9rem; }}
  .badge {{ display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }}
  .badge-pass {{ background: #1b3a22; color: #3fb950; }}
  .badge-fail {{ background: #3a1b1b; color: #f85149; }}
  .badge-warn {{ background: #3a2e1b; color: #d29922; }}
</style>
</head>
<body>
<h1>Pipeline Report: {esc(npc_key)}</h1>
<p class="meta">Profile: {esc(profile)} | Target: {esc(target_stage)} | Generated: {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}</p>
<hr>
<h2>Executive Summary</h2>
<p><strong>Dataset Quality:</strong> {esc(quality_pass)}</p>
<p><strong>Runtime Win Rate:</strong> {esc(wr)}</p>
<p><strong>Training Runs:</strong> {esc(runs_count)}</p>
<p><strong>Integration Health:</strong> <span class="badge {"badge-pass" if int_ok else "badge-fail"}">{"All green" if int_ok else "Blockers"}</span></p>
<hr>
{body}
</body>
</html>"""


# ── Next actions builder ─────────────────────────────────────────────


def _build_next_actions(
    quality: dict[str, Any],
    feedback: dict[str, Any],
    training: dict[str, Any],
    integration: dict[str, Any],
) -> list[dict[str, str]]:
    """Generate recommended next actions from current state."""
    actions: list[dict[str, str]] = []

    if not quality.get("available") or not quality.get("is_pass"):
        actions.append(
            {
                "priority": "high",
                "action": "Run dataset-eval gate",
                "command": "./ucore dataset-eval data/npcs/specs/<npc>.json --technique ollama --mode fast --judge-model qwen2.5:7b",
                "reason": "Dataset quality gate not passed",
            }
        )
    elif quality.get("pass_rate", 1.0) < 1.0:
        actions.append(
            {
                "priority": "medium",
                "action": "Repair dataset quality",
                "command": "./ucore generate-ollama data/npcs/specs/<npc>.json --model qwen2.5:7b --repair data/datasets/<npc>/ollama/quality_failures.json",
                "reason": f"Quality pass rate is {quality.get('pass_rate', 0):.0%}",
            }
        )

    if not feedback.get("available"):
        actions.append(
            {
                "priority": "high",
                "action": "Run runtime evaluation",
                "command": "./ucore evaluate --baseline .models/llama-3.2-3b-instruct-q4_k_m.gguf --candidate artifacts/exports/<npc>/<npc>-lora-f16.gguf --base-model .models/llama-3.2-3b-instruct-q4_k_m.gguf --spec data/npcs/specs/<npc>.json --report-html --judge --judge-model qwen2.5:7b",
                "reason": "No runtime eval results available",
            }
        )
    else:
        win_rate = feedback.get("overall_win_rate")
        candidate_words = feedback.get("avg_candidate_words")
        baseline_words = feedback.get("avg_baseline_words")
        weak = feedback.get("weak_concepts") or []
        if win_rate is not None and win_rate < 0.5:
            if (
                candidate_words is not None
                and baseline_words
                and candidate_words < baseline_words * 0.65
            ):
                actions.append(
                    {
                        "priority": "high",
                        "action": "Repair runtime answer density and specificity",
                        "command": "Add targeted 35-55 word / 2-3 sentence examples for weak concepts, re-sanitize, re-gate, retrain/export, then re-run base+LoRA eval",
                        "reason": f"Runtime win rate is {win_rate:.0%}; candidate avg words {candidate_words:.1f} vs baseline {baseline_words:.1f}",
                    }
                )
            elif weak:
                actions.append(
                    {
                        "priority": "high",
                        "action": "Repair weak runtime concepts",
                        "command": "Use artifacts/eval/results/feedback/<npc>.json weak_concepts to patch targeted dataset rows, then re-run sanitize/gate/train/eval",
                        "reason": f"Runtime win rate is {win_rate:.0%}; weak concepts: {', '.join(weak[:6])}",
                    }
                )
            else:
                actions.append(
                    {
                        "priority": "high",
                        "action": "Improve runtime candidate before promotion",
                        "command": "Inspect runtime eval report and repair the strongest failure mode before parameter comparison",
                        "reason": f"Runtime win rate is {win_rate:.0%}",
                    }
                )

    if not integration.get("ok"):
        blockers = integration.get("blockers", [])
        for b in blockers:
            actions.append(
                {
                    "priority": "high",
                    "action": f"Fix integration: {b.get('integration', 'unknown')}",
                    "command": f"Investigate: {b.get('reason', 'unknown issue')}",
                    "reason": "Integration health check failed",
                }
            )

    # If everything looks good, suggest comparison experiments.
    win_rate = feedback.get("overall_win_rate") if feedback.get("available") else None
    if (
        quality.get("available")
        and training.get("available")
        and feedback.get("available")
        and (win_rate is not None and win_rate >= 0.5)
    ):
        actions.append(
            {
                "priority": "low",
                "action": "Run parameter comparison experiments",
                "command": "Modify training preset (fast-3b -> fast-1.7b, adjust LoRA rank/alpha, vary batch size) and re-run pipeline",
                "reason": "Pipeline is stable — ready for parameter exploration",
            }
        )

    if not actions:
        actions.append(
            {
                "priority": "info",
                "action": "All systems nominal",
                "command": "No action required",
                "reason": "Pipeline is fully green",
            }
        )

    return actions


# ── Main build entrypoint ────────────────────────────────────────────


def build_pipeline_bundle(
    *,
    npc_key: str,
    profile: str = "npc-production-grounded",
    technique: str | None = None,
    target_stage: str = "evaluate",
    report_dir: str | Path | None = None,
    data_root: str | Path | None = None,
    artifact_index: str | Path | None = None,
    run_index: str | Path | None = None,
) -> dict[str, Any]:
    """Build a full pipeline report bundle.

    Returns:
        Dict with bundle metadata and paths.
    """
    root = Path(data_root or PROJECT_ROOT)

    # 1. Resolve the PipelineRunSpec
    from src.core.orchestration.run_spec import resolve_pipeline_run_spec

    effective_technique = technique or "ollama"
    run_spec = resolve_pipeline_run_spec(
        npc_key=npc_key,
        profile=profile,
        technique=effective_technique,
        target_stage=target_stage,
        data_root=root,
    )

    resolved_report_dir = (
        Path(report_dir)
        if report_dir is not None
        else root / run_spec.to_dict()["paths"]["report_dir"]
    )

    # 2. Run integration audit (uses real PROJECT_ROOT for strategy file)
    from src.core.ops.integration_audit import audit_integrations

    integration = audit_integrations(profile=profile)

    # 3. Collect stage fragments
    resolved_artifact_index = Path(artifact_index) if artifact_index else None
    resolved_run_index = Path(run_index) if run_index else None
    stage_fragments = _collect_raw_stage_fragments(
        npc_key,
        effective_technique,
        root,
        artifact_index=resolved_artifact_index,
        run_index=resolved_run_index,
    )
    artifact_stages = _collect_artifact_stages(
        npc_key,
        resolved_artifact_index,
        root,
    )

    # 4. Spec readiness (best-effort check)
    spec_ok = None
    spec_path = root / "data" / "npcs" / "specs" / f"{npc_key}.json"
    if spec_path.exists():
        try:
            spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
            spec_ok = bool(spec_data.get("npc_key"))
        except (json.JSONDecodeError, OSError):
            spec_ok = False

    # 5. Build summary markdown
    summary_md = _build_summary_md(
        npc_key,
        profile,
        target_stage,
        run_spec.to_dict(),
        integration,
        stage_fragments,
        artifact_stages,
        spec_ok,
    )

    # 6. Build next actions
    next_actions = _build_next_actions(
        stage_fragments.get("dataset_quality", {}),
        stage_fragments.get("runtime_eval", {}),
        stage_fragments.get("training", {}),
        integration,
    )

    # 7. Build index HTML
    index_html = _build_index_html(
        npc_key,
        profile,
        target_stage,
        summary_md,
        run_spec.to_dict(),
        integration,
        stage_fragments,
    )

    # 8. Write everything
    resolved_report_dir.mkdir(parents=True, exist_ok=True)

    # Write run spec
    run_spec.write_json(resolved_report_dir / "pipeline_run_spec.json")

    # Write stage status
    stage_status = {
        "npc_key": npc_key,
        "profile": profile,
        "target_stage": target_stage,
        "spec_ok": spec_ok,
        "artifact_stages": artifact_stages,
        "stage_fragments": {
            k: {
                "available": v.get("available", False),
                **(v if v.get("available") else {"reason": v.get("reason", "unknown")}),
            }
            for k, v in stage_fragments.items()
        },
    }
    _write_json(resolved_report_dir / "stage_status.json", stage_status)

    # Write integration health
    _write_json(resolved_report_dir / "integration_health.json", integration)

    # Write dataset quality fragment
    quality = stage_fragments.get("dataset_quality", {})
    _write_json(resolved_report_dir / "dataset_quality.json", quality)

    # Write runtime eval fragment
    feedback = stage_fragments.get("runtime_eval", {})
    _write_json(resolved_report_dir / "runtime_eval_report.json", feedback)

    # Write training fragment
    training = stage_fragments.get("training", {})
    _write_json(resolved_report_dir / "training_report.json", training)

    # Write summary markdown
    (resolved_report_dir / "summary.md").write_text(summary_md, encoding="utf-8")

    # Write index HTML
    (resolved_report_dir / "index.html").write_text(index_html, encoding="utf-8")

    # Write next actions
    _write_json(resolved_report_dir / "next_actions.json", next_actions)

    runtime_win_rate = feedback.get("overall_win_rate") if feedback.get("available") else None
    bundle_ready = bool(
        integration.get("ok", False)
        and quality.get("available", False)
        and quality.get("is_pass", False)
        and training.get("available", False)
        and feedback.get("available", False)
        and runtime_win_rate is not None
        and runtime_win_rate >= 0.5
    )

    return {
        "npc_key": npc_key,
        "profile": profile,
        "target_stage": target_stage,
        "report_dir": str(resolved_report_dir),
        "ok": bundle_ready,
        "run_spec": run_spec.to_dict(),
        "integration_audit": integration,
        "stage_fragments": stage_status["stage_fragments"],
        "summary": summary_md[:200] + "...",
    }


def _write_json(path: Path, data: Any) -> None:
    """Write JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
