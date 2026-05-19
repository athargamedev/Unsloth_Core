#!/usr/bin/env python3
"""
compare_quality_gates.py — Side-by-side comparison of DeepEval and PeerLM quality gates.

Compares NPC dataset quality evaluations from two sources:
  - DeepEval (existing, local Ollama-based judge)
  - PeerLM (complementary blind judge)

Produces a markdown comparison report with agreement analysis,
per-category breakdowns, per-metric comparisons, and actionable recommendations.

Usage:
    python scripts/compare_quality_gates.py \\
        --deepeval-summary subjects/datasets/astronomy_guide/ollama/quality_summary.json \\
        --deepeval-failures subjects/datasets/astronomy_guide/ollama/quality_failures.json \\
        --peerlm-results subjects/datasets/astronomy_guide/ollama/peerlm_eval_results.json \\
        --output subjects/datasets/astronomy_guide/ollama/quality_gate_comparison.md \\
        [--html] [--open]
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from _config import paths


# ── Helpers ──────────────────────────────────────────────────────────────────


def load_json(path: str | Path) -> Any:
    """Load and return JSON from a file path. Exits on failure."""
    p = Path(path)
    if not p.exists():
        print(f"[COMPARE] Error: File not found: {p}", file=sys.stderr)
        sys.exit(1)
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def safe_get(d: dict, *keys: str, default: Any = None) -> Any:
    """Safely traverse a nested dict, returning *default* if any key is missing."""
    current: Any = d
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
            if current is None:
                return default
        else:
            return default
    return current


def format_pct(value: float) -> str:
    """Format a float between 0 and 1 as a percentage string."""
    return f"{value:.1%}"


def format_delta(de_val: float | None, pl_val: float | None) -> str:
    """Return the signed percentage delta between two pass rates."""
    if de_val is None and pl_val is None:
        return "N/A"
    if de_val is None:
        return f"+{pl_val:.1%}"
    if pl_val is None:
        return f"-{de_val:.1%}"
    d = pl_val - de_val
    return f"{d:+.1%}"


# ── Metadata extraction ──────────────────────────────────────────────────────


def extract_npc_key(
    deepeval_summary: dict | None,
    peerlm_results: dict | None,
    args: argparse.Namespace,
) -> str:
    """Extract the NPC key from the most authoritative available source."""
    if args.npc_key:
        return args.npc_key
    if deepeval_summary and "npc_key" in deepeval_summary:
        return deepeval_summary["npc_key"]
    if peerlm_results and "npc_key" in peerlm_results:
        return peerlm_results["npc_key"]
    return "unknown"


def extract_technique(
    deepeval_summary: dict | None,
    peerlm_results: dict | None,
    args: argparse.Namespace,
) -> str:
    """Extract the generation technique from the most authoritative available source."""
    if args.technique:
        return args.technique
    if deepeval_summary and "technique" in deepeval_summary:
        return deepeval_summary["technique"]
    if peerlm_results and "technique" in peerlm_results:
        return peerlm_results["technique"]
    return "unknown"


# ── Agreement analysis ───────────────────────────────────────────────────────


def compute_agreement(
    deepeval_failures: list[dict],
    peerlm_results: dict | None,
) -> dict:
    """Compare DeepEval and PeerLM results test-by-test where they overlap.

    Returns a dict with:
      total_overlap, agreed_count, agreement_rate,
      deepeval_fail_peerlm_pass, deepeval_pass_peerlm_fail,
      disagreements (full detail).
    """
    result: dict[str, Any] = {
        "total_overlap": 0,
        "agreed_count": 0,
        "agreement_rate": None,
        "deepeval_fail_peerlm_pass": [],
        "deepeval_pass_peerlm_fail": [],
        "disagreements": [],
    }

    if not peerlm_results or not deepeval_failures:
        return result

    # Build DeepEval fail set keyed by test_name
    de_fail: dict[str, dict] = {}
    for f in deepeval_failures:
        tn = f.get("test_name", "")
        if tn:
            de_fail[tn] = {
                "test_name": tn,
                "category": safe_get(f, "metadata", "category", default="unknown"),
                "metric": safe_get(f, "metric", "name", default="unknown"),
                "score": safe_get(f, "metric", "score", default=0),
                "threshold": safe_get(f, "metric", "threshold", default=0.85),
                "reason": safe_get(f, "metric", "reason", default=""),
            }

    # Build PeerLM pass/fail map from the results list
    peerlm_results_list = peerlm_results.get("results", [])
    pl_pass: dict[str, bool] = {}
    pl_details: dict[str, dict] = {}
    for r in peerlm_results_list:
        tn = r.get("test_name", "")
        if tn:
            pl_pass[tn] = r.get("passed", False)
            pl_details[tn] = {
                "category": r.get("category", "unknown"),
                "judge_scores": r.get("judge_scores", {}),
                "judge_reason": r.get("judge_reason", ""),
            }

    overlap = set(de_fail.keys()) & set(pl_pass.keys())
    result["total_overlap"] = len(overlap)

    agreed = 0
    for tn in overlap:
        df = de_fail[tn]
        de_failed = True  # It's in the failures list
        pl_passed = pl_pass[tn]

        if de_failed == (not pl_passed):
            agreed += 1
        else:
            detail = {
                "test_name": tn,
                "category": df.get("category")
                or pl_details[tn].get("category", "unknown"),
                "deepeval_passed": not de_failed,
                "peerlm_passed": pl_passed,
                "deepeval_metric": df.get("metric"),
                "deepeval_score": df.get("score"),
                "deepeval_threshold": df.get("threshold"),
                "deepeval_reason": df.get("reason"),
                "peerlm_scores": pl_details[tn].get("judge_scores", {}),
                "peerlm_reason": pl_details[tn].get("judge_reason", ""),
            }

            if de_failed and pl_passed:
                result["deepeval_fail_peerlm_pass"].append(detail)
            else:
                result["deepeval_pass_peerlm_fail"].append(detail)
            result["disagreements"].append(detail)

    result["agreed_count"] = agreed
    if overlap:
        result["agreement_rate"] = agreed / len(overlap)

    return result


# ── Markdown report ──────────────────────────────────────────────────────────


def generate_markdown_report(
    deepeval_summary: dict | None,
    deepeval_failures: list[dict] | None,
    peerlm_results: dict | None,
    npc_key: str,
    technique: str,
) -> str:
    """Generate a side-by-side comparison report in markdown."""
    now = datetime.now(timezone.utc).isoformat()
    lines: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines.append(f"# Quality Gate Comparison: {npc_key}")
    lines.append("")
    lines.append(f"- **NPC Key:** {npc_key}")
    lines.append(f"- **Technique:** {technique}")
    lines.append(f"- **Generated:** {now}")
    lines.append("")

    de_judge = (
        safe_get(deepeval_summary, "judge_model", default="unknown")
        if deepeval_summary
        else "N/A"
    )
    pl_judge = (
        safe_get(peerlm_results, "judge_model", default="unknown")
        if peerlm_results
        else "N/A"
    )
    pl_generator = (
        safe_get(peerlm_results, "generator_model", default="unknown")
        if peerlm_results
        else "N/A"
    )

    lines.append(f"- **DeepEval Judge:** {de_judge}")
    lines.append(f"- **PeerLM Judge:** {pl_judge}")
    lines.append(f"- **PeerLM Generator:** {pl_generator}")
    lines.append("")

    # ── Overall Summary ─────────────────────────────────────────────────────
    lines.append("## Overall Summary")
    lines.append("")
    lines.append("| Metric | DeepEval | PeerLM | Δ |")
    lines.append("|--------|----------|--------|---|")

    de_total = safe_get(deepeval_summary, "total", default=0) if deepeval_summary else 0
    de_passed = safe_get(deepeval_summary, "passed", default=0) if deepeval_summary else 0
    de_failed = safe_get(deepeval_summary, "failed", default=0) if deepeval_summary else 0
    de_rate = safe_get(deepeval_summary, "pass_rate", default=0.0) if deepeval_summary else 0.0

    has_peerlm = peerlm_results is not None

    if has_peerlm:
        pl_total = safe_get(peerlm_results, "total", default=0)
        pl_passed = safe_get(peerlm_results, "passed", default=0)
        pl_failed = safe_get(peerlm_results, "failed", default=0)
        pl_rate = safe_get(peerlm_results, "pass_rate", default=0.0)

        lines.append(f"| Total Tests | {de_total} | {pl_total} | {pl_total - de_total} |")
        lines.append(
            f"| Passed | {de_passed} | {pl_passed} | {pl_passed - de_passed} |"
        )
        lines.append(
            f"| Failed | {de_failed} | {pl_failed} | {pl_failed - de_failed} |"
        )
        lines.append(
            f"| Pass Rate | {format_pct(de_rate)} | {format_pct(pl_rate)} |"
            f" {format_delta(de_rate, pl_rate)} |"
        )
    else:
        for label, val in [
            ("Total Tests", str(de_total)),
            ("Passed", str(de_passed)),
            ("Failed", str(de_failed)),
            ("Pass Rate", format_pct(de_rate)),
        ]:
            lines.append(f"| {label} | {val} | N/A | N/A |")
    lines.append("")

    if not has_peerlm:
        lines.append(
            "> **Note:** PeerLM results were not provided. Only DeepEval data is shown."
        )
        lines.append("")

    # ── Per-Category Comparison ─────────────────────────────────────────────
    lines.append("## Per-Category Comparison")
    lines.append("")

    de_cats: dict = safe_get(deepeval_summary, "categories", default={}) or {}
    pl_cats: dict = safe_get(peerlm_results, "categories", default={}) or {}
    all_cats = sorted(set(list(de_cats.keys()) + list(pl_cats.keys())))

    if all_cats:
        lines.append("| Category | DeepEval Pass Rate | PeerLM Pass Rate | Δ |")
        lines.append("|----------|-------------------|-----------------|---|")
        for cat in all_cats:
            dc = de_cats.get(cat, {})
            pc = pl_cats.get(cat, {})
            de_cr: float | None = dc.get("pass_rate") if dc else None
            pl_cr: float | None = pc.get("pass_rate") if pc else None
            de_str = format_pct(de_cr) if de_cr is not None else "N/A"
            pl_str = format_pct(pl_cr) if pl_cr is not None else "N/A"
            lines.append(f"| {cat} | {de_str} | {pl_str} | {format_delta(de_cr, pl_cr)} |")
        lines.append("")

    # ── Per-Metric Comparison ───────────────────────────────────────────────
    lines.append("## Per-Metric Comparison")
    lines.append("")

    de_metrics: dict = safe_get(deepeval_summary, "metrics", default={}) or {}
    pl_scores: dict = safe_get(peerlm_results, "overall_scores", default={}) or {}
    all_metrics = sorted(set(list(de_metrics.keys()) + list(pl_scores.keys())))

    if all_metrics:
        lines.append(
            "| Metric | DeepEval Avg Score | DeepEval Pass Rate"
            " | PeerLM Avg Score | PeerLM Max |"
        )
        lines.append(
            "|--------|-------------------|-------------------"
            "|-----------------|------------|"
        )
        for m in all_metrics:
            dm = de_metrics.get(m, {})
            pm = pl_scores.get(m, {})

            de_sc = dm.get("average_score") if dm else None
            de_pr = dm.get("pass_rate") if dm else None
            pl_av = pm.get("average") if pm else None
            pl_mx = pm.get("max") if pm else None

            de_sc_s = f"{de_sc:.4f}" if isinstance(de_sc, (int, float)) else "N/A"
            de_pr_s = format_pct(de_pr) if isinstance(de_pr, (int, float)) else "N/A"
            pl_av_s = f"{pl_av:.2f}" if isinstance(pl_av, (int, float)) else "N/A"
            pl_mx_s = str(pl_mx) if pl_mx is not None else "N/A"

            lines.append(
                f"| {m} | {de_sc_s} | {de_pr_s} | {pl_av_s} | {pl_mx_s} |"
            )
        lines.append("")

    # ── Agreement Analysis ──────────────────────────────────────────────────
    lines.append("## Agreement Analysis")
    lines.append("")

    if has_peerlm and deepeval_failures:
        agreement = compute_agreement(deepeval_failures, peerlm_results)

        overlap = agreement["total_overlap"]
        agreed = agreement["agreed_count"]
        rate = agreement["agreement_rate"]

        lines.append(f"- **Overlapping tests evaluated by both:** {overlap}")
        lines.append(f"- **Agreements (both judges agree):** {agreed}")
        lines.append(
            f"- **Agreement rate:** {format_pct(rate) if rate is not None else 'N/A'}"
        )
        lines.append("")

        d_fail_p_pass = agreement["deepeval_fail_peerlm_pass"]
        d_pass_p_fail = agreement["deepeval_pass_peerlm_fail"]

        lines.append(
            f"- **DeepEval failed / PeerLM passed:** {len(d_fail_p_pass)} test(s)"
        )
        lines.append(
            f"- **DeepEval passed / PeerLM failed:** {len(d_pass_p_fail)} test(s)"
        )
        lines.append("")

        if agreement["disagreements"]:
            lines.append("### Disagreement Details")
            lines.append("")
            lines.append(
                "| Test Name | Category | DeepEval Verdict"
                " | PeerLM Verdict | Notes |"
            )
            lines.append(
                "|-----------|----------|-----------------"
                "|---------------|-------|"
            )
            for d in agreement["disagreements"]:
                de_v = "❌ FAIL" if not d.get("deepeval_passed", True) else "✅ PASS"
                pl_v = "✅ PASS" if d.get("peerlm_passed", False) else "❌ FAIL"
                notes = d.get("deepeval_reason", "") or d.get("peerlm_reason", "")
                short = (notes[:80] + "...") if len(notes) > 80 else notes
                lines.append(f"| {d['test_name']} | {d['category']} | {de_v} | {pl_v} | {short} |")
            lines.append("")
    else:
        lines.append(
            "*PeerLM results or DeepEval failures not available"
            " for agreement analysis.*"
        )
        lines.append("")

    # ── Failure Analysis ────────────────────────────────────────────────────
    lines.append("## DeepEval Failure Analysis")
    lines.append("")

    if deepeval_failures:
        lines.append(
            f"**{len(deepeval_failures)} failing test(s) detected by DeepEval.**"
        )
        lines.append("")
        lines.append(
            "| Test Name | Category | Metric | Score | Threshold | Reason |"
        )
        lines.append(
            "|-----------|----------|--------|-------|-----------|--------|"
        )
        for f in deepeval_failures:
            tn = f.get("test_name", "unknown")
            cat = safe_get(f, "metadata", "category", default="unknown")
            mn = safe_get(f, "metric", "name", default="unknown")
            sc = safe_get(f, "metric", "score", default=0)
            th = safe_get(f, "metric", "threshold", default=0.85)
            rs = safe_get(f, "metric", "reason", default="")

            sc_s = f"{sc:.4f}" if isinstance(sc, (int, float)) else str(sc)
            th_s = f"{th:.4f}" if isinstance(th, (int, float)) else str(th)
            rs_s = (rs[:100] + "...") if len(rs) > 100 else rs

            lines.append(f"| {tn} | {cat} | {mn} | {sc_s} | {th_s} | {rs_s} |")
        lines.append("")
    elif deepeval_summary:
        lines.append("*No failures reported by DeepEval.*")
        lines.append("")
    else:
        lines.append("*DeepEval data not available.*")
        lines.append("")

    # ── Recommendations ─────────────────────────────────────────────────────
    lines.append("## Recommendations")
    lines.append("")

    recs: list[str] = []

    if deepeval_summary and de_rate < 0.7:
        recs.append(
            f"- ⚠️ **Low DeepEval pass rate ({format_pct(de_rate)}).**"
            " Review dataset quality and consider regeneration with improved"
            " prompts or additional reference material."
        )

    if has_peerlm:
        pl_rate_v = peerlm_results.get("pass_rate", 1.0)
        if pl_rate_v < 0.7:
            recs.append(
                f"- ⚠️ **Low PeerLM pass rate ({format_pct(pl_rate_v)}).**"
                " The blind judge evaluation indicates quality concerns."
                " Cross-reference with DeepEval failures."
            )

    if has_peerlm and deepeval_failures:
        agr = compute_agreement(deepeval_failures, peerlm_results)
        if agr["agreement_rate"] is not None and agr["agreement_rate"] < 0.6:
            recs.append(
                f"- ⚠️ **Low agreement rate ({format_pct(agr['agreement_rate'])}).**"
                " The two evaluation systems disagree significantly. Investigate"
                " individual disagreement cases to determine which judge is more"
                " reliable for this dataset."
            )

        if agr["deepeval_fail_peerlm_pass"]:
            recs.append(
                f"- 🔍 **{len(agr['deepeval_fail_peerlm_pass'])} test(s)"
                " where DeepEval failed but PeerLM passed.**"
                " Review these cases — DeepEval may be overly strict on certain"
                " metrics, or PeerLM may be missing context-specific failures."
            )

        if agr["deepeval_pass_peerlm_fail"]:
            recs.append(
                f"- 🔍 **{len(agr['deepeval_pass_peerlm_fail'])} test(s)"
                " where DeepEval passed but PeerLM failed.**"
                " These may indicate blind spots in the DeepEval evaluation."
                " Consider adding new metrics or adjusting thresholds."
            )

    # Category weakness
    weak_de = [
        c for c, v in de_cats.items() if isinstance(v, dict) and v.get("pass_rate", 1) < 0.7
    ]
    if weak_de:
        recs.append(
            f"- 🎯 **Weak categories in DeepEval:** {', '.join(weak_de)}."
            " Focus regeneration efforts on these categories."
        )

    weak_pl = [
        c for c, v in pl_cats.items() if isinstance(v, dict) and v.get("pass_rate", 1) < 0.7
    ]
    if weak_pl:
        recs.append(
            f"- 🎯 **Weak categories in PeerLM:** {', '.join(weak_pl)}."
            " Consider additional training examples for these categories."
        )

    if not recs:
        recs.append(
            "- ✅ **All quality gates passed.** The dataset appears to meet"
            " quality standards across both evaluation systems."
        )

    recs.append(
        "- 📊 **Next steps:** Run `./ucore dataset-eval` with a different judge"
        " model for additional validation, or proceed to training with"
        " `./ucore train`."
    )

    for r in recs:
        lines.append(r)
        lines.append("")

    return "\n".join(lines)


# ── HTML report ──────────────────────────────────────────────────────────────


def generate_html_report(
    deepeval_summary: dict | None,
    deepeval_failures: list[dict] | None,
    peerlm_results: dict | None,
    npc_key: str,
    technique: str,
) -> str:
    """Generate a standalone HTML report with Chart.js visualizations."""
    now = datetime.now(timezone.utc).isoformat()

    de_judge = (
        safe_get(deepeval_summary, "judge_model", default="N/A")
        if deepeval_summary
        else "N/A"
    )
    pl_judge = (
        safe_get(peerlm_results, "judge_model", default="N/A")
        if peerlm_results
        else "N/A"
    )

    de_total = safe_get(deepeval_summary, "total", default=0) if deepeval_summary else 0
    de_passed = safe_get(deepeval_summary, "passed", default=0) if deepeval_summary else 0
    de_rate = safe_get(deepeval_summary, "pass_rate", default=0.0) if deepeval_summary else 0.0
    de_cats: dict = safe_get(deepeval_summary, "categories", default={}) or {}
    de_metrics: dict = safe_get(deepeval_summary, "metrics", default={}) or {}

    has_peerlm = peerlm_results is not None
    if has_peerlm:
        pl_total = safe_get(peerlm_results, "total", default=0)
        pl_passed = safe_get(peerlm_results, "passed", default=0)
        pl_rate = safe_get(peerlm_results, "pass_rate", default=0.0)
        pl_cats: dict = safe_get(peerlm_results, "categories", default={}) or {}
        pl_scores: dict = safe_get(peerlm_results, "overall_scores", default={}) or {}
    else:
        pl_total = 0
        pl_passed = 0
        pl_rate = 0.0
        pl_cats = {}
        pl_scores = {}

    all_cats = sorted(set(list(de_cats.keys()) + list(pl_cats.keys())))
    all_metrics = sorted(set(list(de_metrics.keys()) + list(pl_scores.keys())))

    # Compute agreement once
    agreement: dict = {}
    if has_peerlm and deepeval_failures:
        agreement = compute_agreement(deepeval_failures, peerlm_results)

    has_failures = bool(deepeval_failures)

    # ── Build summary card values ───────────────────────────────────────────
    de_rate_color = "green" if de_rate >= 0.7 else "red"
    pl_rate_color = "green" if pl_rate >= 0.7 else "red"
    agreement_rate = agreement.get("agreement_rate")
    agreement_str = format_pct(agreement_rate) if agreement_rate is not None else "N/A"
    disagreement_count = len(agreement.get("disagreements", []))

    # ── Failure rows ────────────────────────────────────────────────────────
    failure_rows = ""
    if deepeval_failures:
        for f in deepeval_failures[:20]:
            tn = html.escape(f.get("test_name", "unknown"))
            cat = html.escape(safe_get(f, "metadata", "category", default="unknown"))
            mn = html.escape(safe_get(f, "metric", "name", default="unknown"))
            sc = safe_get(f, "metric", "score", default=0)
            th = safe_get(f, "metric", "threshold", default=0.85)
            rs = html.escape(safe_get(f, "metric", "reason", default=""))
            sc_s = f"{sc:.4f}" if isinstance(sc, (int, float)) else str(sc)
            th_s = f"{th:.4f}" if isinstance(th, (int, float)) else str(th)
            failure_rows += f"""\
            <tr>
              <td>{tn}</td>
              <td>{cat}</td>
              <td>{mn}</td>
              <td class="fail-cell">{sc_s}</td>
              <td>{th_s}</td>
              <td>{rs}</td>
            </tr>
"""

    # ── Disagreement rows ───────────────────────────────────────────────────
    disagreement_rows = ""
    for d in agreement.get("disagreements", []):
        tn = html.escape(d.get("test_name", ""))
        cat = html.escape(d.get("category", ""))
        de_v = "FAIL" if not d.get("deepeval_passed", True) else "PASS"
        pl_v = "PASS" if d.get("peerlm_passed", False) else "FAIL"
        notes = html.escape(d.get("deepeval_reason", "") or d.get("peerlm_reason", ""))
        de_cls = "fail-cell" if not d.get("deepeval_passed", True) else "pass-cell"
        pl_cls = "pass-cell" if d.get("peerlm_passed", False) else "fail-cell"
        disagreement_rows += f"""\
            <tr>
              <td>{tn}</td>
              <td>{cat}</td>
              <td class="{de_cls}">{de_v}</td>
              <td class="{pl_cls}">{pl_v}</td>
              <td>{notes}</td>
            </tr>
"""

    # ── Chart data (inline JSON) ────────────────────────────────────────────
    cat_labels = all_cats
    de_cat_data = [de_cats.get(c, {}).get("pass_rate", 0) for c in cat_labels]
    pl_cat_data = [
        pl_cats.get(c, {}).get("pass_rate", 0) if pl_cats else None for c in cat_labels
    ]

    metric_labels = all_metrics
    de_metric_data = [
        (
            de_metrics.get(m, {}).get("average_score", 0)
            if isinstance(de_metrics.get(m, {}).get("average_score"), (int, float))
            else 0
        )
        for m in metric_labels
    ]
    pl_metric_data = [
        (
            pl_scores.get(m, {}).get("average", 0)
            if isinstance(pl_scores.get(m, {}).get("average"), (int, float))
            else 0
        )
        for m in metric_labels
    ]

    cat_labels_j = json.dumps(cat_labels)
    de_cat_j = json.dumps(de_cat_data)
    pl_cat_j = json.dumps(pl_cat_data)
    metric_labels_j = json.dumps(metric_labels)
    de_metric_j = json.dumps(de_metric_data)
    pl_metric_j = json.dumps(pl_metric_data)

    # ── Overall summary values ──────────────────────────────────────────────
    de_total_s = str(de_total)
    pl_total_s = str(pl_total) if has_peerlm else "N/A"
    de_passed_s = str(de_passed)
    pl_passed_s = str(pl_passed) if has_peerlm else "N/A"
    de_failed_s = str(de_total - de_passed)
    pl_failed_s = str(pl_total - pl_passed) if has_peerlm else "N/A"
    de_rate_s = format_pct(de_rate)
    pl_rate_s = format_pct(pl_rate) if has_peerlm else "N/A"
    delta_rate_s = format_delta(de_rate, pl_rate) if has_peerlm else "N/A"
    delta_total_s = str(pl_total - de_total) if has_peerlm else "N/A"
    delta_passed_s = str(pl_passed - de_passed) if has_peerlm else "N/A"
    delta_failed_s = str((pl_total - pl_passed) - (de_total - de_passed)) if has_peerlm else "N/A"

    # ── Recommendations ─────────────────────────────────────────────────────
    rec_items: list[str] = []
    if de_rate < 0.7:
        rec_items.append(
            f"<li>⚠️ <strong>Low DeepEval pass rate ({format_pct(de_rate)}).</strong> "
            "Review dataset quality and consider regeneration with improved "
            "prompts or additional reference material.</li>"
        )
    if has_peerlm and pl_rate < 0.7:
        rec_items.append(
            f"<li>⚠️ <strong>Low PeerLM pass rate ({format_pct(pl_rate)}).</strong> "
            "The blind judge evaluation indicates quality concerns. "
            "Cross-reference with DeepEval failures.</li>"
        )
    if (
        agreement.get("agreement_rate") is not None
        and agreement["agreement_rate"] < 0.6
    ):
        rec_items.append(
            f"<li>⚠️ <strong>Low agreement rate ({format_pct(agreement['agreement_rate'])}).</strong> "
            "The two evaluation systems disagree significantly. "
            "Investigate individual disagreement cases.</li>"
        )
    if agreement.get("deepeval_fail_peerlm_pass"):
        rec_items.append(
            f"<li>🔍 <strong>{len(agreement['deepeval_fail_peerlm_pass'])} test(s)</strong> "
            "where DeepEval failed but PeerLM passed. "
            "These may indicate DeepEval is overly strict.</li>"
        )
    if agreement.get("deepeval_pass_peerlm_fail"):
        rec_items.append(
            f"<li>🔍 <strong>{len(agreement['deepeval_pass_peerlm_fail'])} test(s)</strong> "
            "where DeepEval passed but PeerLM failed. "
            "These may indicate blind spots in DeepEval.</li>"
        )
    weak_de_cats = [
        c
        for c, v in de_cats.items()
        if isinstance(v, dict) and v.get("pass_rate", 1) < 0.7
    ]
    if weak_de_cats:
        rec_items.append(
            "<li>🎯 <strong>Weak categories in DeepEval:</strong> "
            f"{', '.join(html.escape(c) for c in weak_de_cats)}. "
            "Focus regeneration efforts on these categories.</li>"
        )
    weak_pl_cats = [
        c
        for c, v in pl_cats.items()
        if isinstance(v, dict) and v.get("pass_rate", 1) < 0.7
    ]
    if weak_pl_cats:
        rec_items.append(
            "<li>🎯 <strong>Weak categories in PeerLM:</strong> "
            f"{', '.join(html.escape(c) for c in weak_pl_cats)}. "
            "Consider additional training examples.</li>"
        )
    if not rec_items:
        rec_items.append(
            "<li>✅ <strong>All quality gates passed.</strong> "
            "The dataset appears to meet quality standards across "
            "both evaluation systems.</li>"
        )
    rec_items.append(
        "<li>📊 <strong>Next steps:</strong> Run <code>./ucore dataset-eval</code> "
        "with a different judge model for additional validation, "
        "or proceed to training with <code>./ucore train</code>.</li>"
    )

    has_peerlm_js = "true" if has_peerlm else "false"
    no_peerlm_banner = ""
    if not has_peerlm:
        no_peerlm_banner = (
            '<div class="disclaimer">⚠️ PeerLM results were not provided. '
            "Only DeepEval data is shown.</div>\n\n"
        )

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quality Gate Comparison — {html.escape(npc_key)}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f7fa;
    color: #1a1a2e;
    padding: 2rem;
  }}
  h1 {{ font-size: 1.8rem; margin-bottom: 0.5rem; }}
  h2 {{ font-size: 1.3rem; margin: 2rem 0 1rem; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.3rem; }}
  .subtitle {{ color: #64748b; margin-bottom: 1.5rem; }}
  table {{
    width: 100%; border-collapse: collapse; margin: 1rem 0 2rem;
    background: white; border-radius: 8px; overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  th, td {{ padding: 0.6rem 1rem; text-align: left; border-bottom: 1px solid #e2e8f0; }}
  th {{ background: #1a1a2e; color: white; font-weight: 600; }}
  tr:hover {{ background: #f1f5f9; }}
  .pass-cell {{ color: #16a34a; font-weight: 600; }}
  .fail-cell {{ color: #dc2626; font-weight: 600; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; margin: 1rem 0 2rem; }}
  .chart-card {{
    background: white; padding: 1rem; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  .chart-card h3 {{ margin-bottom: 0.5rem; font-size: 1rem; }}
  canvas {{ max-height: 300px; }}
  .summary-cards {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem; margin: 1rem 0 2rem;
  }}
  .card {{
    background: white; padding: 1.2rem; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center;
  }}
  .card h3 {{ font-size: 0.85rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
  .card .value {{ font-size: 2rem; font-weight: 700; margin: 0.3rem 0; }}
  .card .sub {{ font-size: 0.8rem; color: #94a3b8; }}
  .note {{ color: #64748b; font-style: italic; margin: 1rem 0; }}
  .disclaimer {{ background: #fef3c7; border: 1px solid #f59e0b; padding: 0.8rem 1rem; border-radius: 6px; margin: 1rem 0; }}
</style>
</head>
<body>

<h1>Quality Gate Comparison: {html.escape(npc_key)}</h1>
<p class="subtitle">
  Technique: <strong>{html.escape(technique)}</strong> &nbsp;|&nbsp;
  DeepEval Judge: <strong>{html.escape(de_judge)}</strong> &nbsp;|&nbsp;
  PeerLM Judge: <strong>{html.escape(pl_judge)}</strong> &nbsp;|&nbsp;
  Generated: {html.escape(now)}
</p>

{no_peerlm_banner}
<div class="summary-cards">
  <div class="card">
    <h3>DeepEval Pass Rate</h3>
    <div class="value" style="color:{de_rate_color}">{de_rate_s}</div>
    <div class="sub">{de_passed_s} / {de_total_s} passed</div>
  </div>
  <div class="card">
    <h3>PeerLM Pass Rate</h3>
    <div class="value" style="color:{pl_rate_color}">{pl_rate_s}</div>
    <div class="sub">{pl_passed_s} / {pl_total_s} passed</div>
  </div>
  <div class="card">
    <h3>Agreement Rate</h3>
    <div class="value">{agreement_str}</div>
    <div class="sub">{disagreement_count} disagreement(s)</div>
  </div>
</div>

<div class="charts">
  <div class="chart-card">
    <h3>Per-Category Pass Rate</h3>
    <canvas id="catChart"></canvas>
  </div>
  <div class="chart-card">
    <h3>Per-Metric Average Score</h3>
    <canvas id="metricChart"></canvas>
  </div>
</div>

<h2>Overall Summary</h2>
<table>
  <thead>
    <tr><th>Metric</th><th>DeepEval</th><th>PeerLM</th><th>Δ</th></tr>
  </thead>
  <tbody>
    <tr><td>Total Tests</td><td>{de_total_s}</td><td>{pl_total_s}</td><td>{delta_total_s}</td></tr>
    <tr><td>Passed</td><td>{de_passed_s}</td><td>{pl_passed_s}</td><td>{delta_passed_s}</td></tr>
    <tr><td>Failed</td><td>{de_failed_s}</td><td>{pl_failed_s}</td><td>{delta_failed_s}</td></tr>
    <tr>
      <td>Pass Rate</td>
      <td class="{"pass-cell" if de_rate >= 0.7 else "fail-cell"}">{de_rate_s}</td>
      <td class="{"pass-cell" if pl_rate >= 0.7 else "fail-cell" if has_peerlm else ""}">{pl_rate_s}</td>
      <td>{delta_rate_s}</td>
    </tr>
  </tbody>
</table>

<h2>Per-Category Comparison</h2>
<table>
  <thead>
    <tr><th>Category</th><th>DeepEval Pass Rate</th><th>PeerLM Pass Rate</th><th>Δ</th></tr>
  </thead>
  <tbody>
"""
    for cat in all_cats:
        dc = de_cats.get(cat, {})
        pc = pl_cats.get(cat, {})
        de_cr: float | None = dc.get("pass_rate") if dc else None
        pl_cr: float | None = pc.get("pass_rate") if pc else None
        de_cr_s = format_pct(de_cr) if de_cr is not None else "N/A"
        pl_cr_s = format_pct(pl_cr) if pl_cr is not None else "N/A"
        de_cls = "pass-cell" if (de_cr is not None and de_cr >= 0.7) else "fail-cell" if de_cr is not None else ""
        pl_cls = "pass-cell" if (pl_cr is not None and pl_cr >= 0.7) else "fail-cell" if pl_cr is not None else ""
        html_out += f"""\
    <tr>
      <td>{html.escape(cat)}</td>
      <td class="{de_cls}">{de_cr_s}</td>
      <td class="{pl_cls}">{pl_cr_s}</td>
      <td>{format_delta(de_cr, pl_cr)}</td>
    </tr>
"""

    html_out += """\
  </tbody>
</table>

<h2>Per-Metric Comparison</h2>
<table>
  <thead>
    <tr>
      <th>Metric</th><th>DeepEval Avg Score</th><th>DeepEval Pass Rate</th>
      <th>PeerLM Avg Score</th><th>PeerLM Max</th>
    </tr>
  </thead>
  <tbody>
"""
    for m in all_metrics:
        dm = de_metrics.get(m, {})
        pm = pl_scores.get(m, {})
        de_sc = dm.get("average_score") if dm else None
        de_pr = dm.get("pass_rate") if dm else None
        pl_av = pm.get("average") if pm else None
        pl_mx = pm.get("max") if pm else None
        de_sc_s = f"{de_sc:.4f}" if isinstance(de_sc, (int, float)) else "N/A"
        de_pr_s = format_pct(de_pr) if isinstance(de_pr, (int, float)) else "N/A"
        pl_av_s = f"{pl_av:.2f}" if isinstance(pl_av, (int, float)) else "N/A"
        pl_mx_s = str(pl_mx) if pl_mx is not None else "N/A"
        html_out += f"""\
    <tr>
      <td>{html.escape(m)}</td>
      <td>{de_sc_s}</td>
      <td>{de_pr_s}</td>
      <td>{pl_av_s}</td>
      <td>{pl_mx_s}</td>
    </tr>
"""

    html_out += """\
  </tbody>
</table>

<h2>Agreement Analysis</h2>
"""
    if has_peerlm and has_failures:
        overlap = agreement.get("total_overlap", 0)
        agreed = agreement.get("agreed_count", 0)
        d_fail_p_pass = len(agreement.get("deepeval_fail_peerlm_pass", []))
        d_pass_p_fail = len(agreement.get("deepeval_pass_peerlm_fail", []))
        html_out += f"""\
<p>
  <strong>Overlap:</strong> {overlap} tests |
  <strong>Agreements:</strong> {agreed} |
  <strong>Rate:</strong> {agreement_str}
</p>
<p>
  <strong>DeepEval FAIL / PeerLM PASS:</strong> {d_fail_p_pass} test(s) &nbsp;|&nbsp;
  <strong>DeepEval PASS / PeerLM FAIL:</strong> {d_pass_p_fail} test(s)
</p>
"""
        if disagreement_rows:
            html_out += """\
<table>
  <thead>
    <tr><th>Test Name</th><th>Category</th><th>DeepEval</th><th>PeerLM</th><th>Notes</th></tr>
  </thead>
  <tbody>
""" + disagreement_rows + """\
  </tbody>
</table>
"""
    else:
        html_out += '<p class="note">PeerLM results or DeepEval failures not available for agreement analysis.</p>\n'

    html_out += """\
<h2>DeepEval Failure Analysis</h2>
"""
    if has_failures:
        html_out += f"""\
<p><strong>{len(deepeval_failures)} failing test(s) detected by DeepEval.</strong></p>
<table>
  <thead>
    <tr><th>Test Name</th><th>Category</th><th>Metric</th><th>Score</th><th>Threshold</th><th>Reason</th></tr>
  </thead>
  <tbody>
""" + failure_rows + """\
  </tbody>
</table>
"""
    elif deepeval_summary:
        html_out += '<p class="note">No failures reported by DeepEval.</p>\n'
    else:
        html_out += '<p class="note">DeepEval data not available.</p>\n'

    html_out += """\
<h2>Recommendations</h2>
<ul>
""" + "\n".join(rec_items) + """\
</ul>

<script>
const hasPeerLM = """ + has_peerlm_js + """;

new Chart(document.getElementById('catChart'), {
  type: 'bar',
  data: {
    labels: """ + cat_labels_j + """,
    datasets: [
      {
        label: 'DeepEval',
        data: """ + de_cat_j + """,
        backgroundColor: 'rgba(59, 130, 246, 0.7)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 1
      },
      {
        label: 'PeerLM',
        data: """ + pl_cat_j + """,
        backgroundColor: 'rgba(139, 92, 246, 0.7)',
        borderColor: 'rgba(139, 92, 246, 1)',
        borderWidth: 1
      }
    ]
  },
  options: {
    responsive: true,
    plugins: { legend: { position: 'top' } },
    scales: {
      y: {
        beginAtZero: true,
        max: 1,
        ticks: { callback: v => (v * 100).toFixed(0) + '%' }
      }
    }
  }
});

new Chart(document.getElementById('metricChart'), {
  type: 'radar',
  data: {
    labels: """ + metric_labels_j + """,
    datasets: [
      {
        label: 'DeepEval Avg Score',
        data: """ + de_metric_j + """,
        backgroundColor: 'rgba(59, 130, 246, 0.2)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 2,
        pointBackgroundColor: 'rgba(59, 130, 246, 1)'
      },
      {
        label: 'PeerLM Avg Score',
        data: """ + pl_metric_j + """,
        backgroundColor: 'rgba(139, 92, 246, 0.2)',
        borderColor: 'rgba(139, 92, 246, 1)',
        borderWidth: 2,
        pointBackgroundColor: 'rgba(139, 92, 246, 1)'
      }
    ]
  },
  options: {
    responsive: true,
    plugins: { legend: { position: 'top' } },
    scales: {
      r: { beginAtZero: true, max: 5 }
    }
  }
});
</script>

</body>
</html>"""

    return html_out


# ── Open file helper ─────────────────────────────────────────────────────────


def open_file(path: str) -> None:
    """Open a file using the system default application."""
    system = sys.platform
    try:
        if system == "darwin":
            subprocess.run(["open", path], check=True)
        elif system == "win32":
            subprocess.run(["start", path], shell=True, check=True)
        else:
            print(
                f"[COMPARE] Report written to: {path}", file=sys.stderr
            )
    except Exception as e:
        print(f"[COMPARE] Could not open report: {e}", file=sys.stderr)


# ── CLI entrypoint ───────────────────────────────────────────────────────────


def main() -> int:
    # Pre-scan sys.argv so that parent dirs for --output exist before
    # argparse.FileType tries to open the file.
    for i, arg in enumerate(sys.argv[:-1]):
        if arg in ("--output", "-o"):
            out_path = Path(sys.argv[i + 1])
            out_path.parent.mkdir(parents=True, exist_ok=True)
            break

    parser = argparse.ArgumentParser(
        description=(
            "Compare NPC dataset quality evaluations from DeepEval and PeerLM."
        )
    )
    parser.add_argument(
        "--deepeval-summary",
        required=True,
        help="Path to DeepEval quality_summary.json",
    )
    parser.add_argument(
        "--deepeval-failures",
        help="Path to DeepEval quality_failures.json (optional)",
    )
    parser.add_argument(
        "--peerlm-results",
        help="Path to PeerLM eval results JSON (optional)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=argparse.FileType("w"),
        default=sys.stdout,
        help="Output report path (default: stdout)",
    )
    parser.add_argument(
        "--npc-key",
        help="Override NPC key (auto-detected from input files)",
    )
    parser.add_argument(
        "--technique",
        help="Override technique (auto-detected from input files)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Also generate a standalone HTML report alongside the markdown report",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        dest="open_report",
        help="Open the report after generation",
    )
    args = parser.parse_args()

    # ── Load inputs ──────────────────────────────────────────────────────
    print(
        f"[COMPARE] Loading DeepEval summary: {args.deepeval_summary}",
        file=sys.stderr,
    )
    deepeval_summary = load_json(args.deepeval_summary)

    deepeval_failures: list[dict] | None = None
    if args.deepeval_failures:
        print(
            f"[COMPARE] Loading DeepEval failures: {args.deepeval_failures}",
            file=sys.stderr,
        )
        raw = load_json(args.deepeval_failures)
        deepeval_failures = raw if isinstance(raw, list) else []
        if not isinstance(raw, list):
            print(
                "[COMPARE] Warning: DeepEval failures file is not a list;"
                " treating as empty.",
                file=sys.stderr,
            )

    peerlm_results: dict | None = None
    if args.peerlm_results:
        print(
            f"[COMPARE] Loading PeerLM results: {args.peerlm_results}",
            file=sys.stderr,
        )
        peerlm_results = load_json(args.peerlm_results)

    # ── Extract metadata ─────────────────────────────────────────────────
    npc_key = extract_npc_key(deepeval_summary, peerlm_results, args)
    technique = extract_technique(deepeval_summary, peerlm_results, args)

    print(f"[COMPARE] NPC Key: {npc_key}", file=sys.stderr)
    print(f"[COMPARE] Technique: {technique}", file=sys.stderr)

    # ── Generate reports ─────────────────────────────────────────────────
    md_content = generate_markdown_report(
        deepeval_summary,
        deepeval_failures,
        peerlm_results,
        npc_key,
        technique,
    )

    args.output.write(md_content)
    out_path = args.output.name
    print(f"[COMPARE] Report written: {out_path}", file=sys.stderr)

    html_path: Path | None = None
    if args.html:
        html_content = generate_html_report(
            deepeval_summary,
            deepeval_failures,
            peerlm_results,
            npc_key,
            technique,
        )
        html_path = Path(out_path).with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html_content, encoding="utf-8")
        print(f"[COMPARE] HTML report written: {html_path}", file=sys.stderr)

    # ── Open if requested ─────────────────────────────────────────────────
    if args.open_report:
        open_file(str(html_path if html_path else out_path))

    print(f"[COMPARE] Done.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
