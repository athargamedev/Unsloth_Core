from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_STRATEGY_PATH = PROJECT_ROOT / "etc" / "npc-production-strategy.yaml"
DEFAULT_PROFILE = "npc-production-grounded"
DENSITY_TARGET_MIN_WORDS = 35
DENSITY_TARGET_MAX_WORDS = 55


def _load_yaml(path: Path = DEFAULT_STRATEGY_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"NPC production strategy config not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"NPC production strategy config must be a mapping: {path}")
    return data


def load_strategy_profile(profile: str = DEFAULT_PROFILE, *, path: Path = DEFAULT_STRATEGY_PATH) -> dict[str, Any]:
    data = _load_yaml(path)
    profiles = data.get("profiles") or {}
    if profile not in profiles:
        available = ", ".join(sorted(profiles)) or "none"
        raise KeyError(f"Unknown NPC strategy profile {profile!r}; available: {available}")
    loaded = dict(profiles[profile] or {})
    loaded["name"] = profile
    return loaded


def list_strategy_profiles(*, path: Path = DEFAULT_STRATEGY_PATH) -> dict[str, Any]:
    return _load_yaml(path).get("profiles") or {}


def density_repair_needed(feedback_data: dict[str, Any], *, min_words: int = DENSITY_TARGET_MIN_WORDS, max_words: int = DENSITY_TARGET_MAX_WORDS) -> dict[str, Any]:
    """Decide whether eval feedback points to bounded density repair.

    This is intentionally strategy-level: it prevents endless concept patching by
    routing terse adapter losses to one named density-repair profile.
    """
    candidate_words = float(feedback_data.get("avg_candidate_words") or feedback_data.get("candidate_avg_words") or 0)
    baseline_words = float(feedback_data.get("avg_baseline_words") or feedback_data.get("baseline_avg_words") or 0)

    # Backward compat: compute aggregates from per-example data if top-level absent
    if candidate_words == 0 and baseline_words == 0:
        per_concept = feedback_data.get("per_concept") or {}
        cand_vals: list[float] = []
        base_vals: list[float] = []
        for info in per_concept.values():
            for ex in info.get("examples", []):
                wc = ex.get("candidate_words")
                if wc is not None: cand_vals.append(float(wc))
                wb = ex.get("baseline_words")
                if wb is not None: base_vals.append(float(wb))
        if cand_vals: candidate_words = sum(cand_vals) / len(cand_vals)
        if base_vals: baseline_words = sum(base_vals) / len(base_vals)

    win_rate = float(feedback_data.get("win_rate") or feedback_data.get("candidate_win_rate") or 0)
    weak_concepts = feedback_data.get("weak_concepts") or []

    too_short_absolute = candidate_words > 0 and candidate_words < min_words
    too_short_relative = baseline_words > 0 and candidate_words > 0 and candidate_words <= baseline_words * 0.65
    losing_or_weak = win_rate < 0.5 or bool(weak_concepts)
    needed = losing_or_weak and (too_short_absolute or too_short_relative)

    return {
        "needed": needed,
        "reason": "candidate_too_terse" if needed else "density_ok_or_not_primary",
        "candidate_words": candidate_words,
        "baseline_words": baseline_words,
        "win_rate": win_rate,
        "target_min_words": min_words,
        "target_max_words": max_words,
        "profile": "npc-density-repair" if needed else None,
    }


def _count_repair(history: list[dict[str, Any]], repair_class: str) -> int:
    return sum(1 for item in history if (item or {}).get("class") == repair_class)


def classify_feedback_cycle(feedback_data: dict[str, Any], *, profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    strategy = load_strategy_profile(profile)
    limits = strategy.get("anti_loop") or {}
    history = feedback_data.get("repair_history") or []
    if not isinstance(history, list):
        history = []

    exact = _count_repair(history, "exact_confident_failure")
    density = _count_repair(history, "density_repair")
    variants = _count_repair(history, "training_preset_variant")

    flags: list[str] = []
    if exact >= int(limits.get("max_exact_confident_failure_repairs", 1)):
        flags.append("exact_confident_repair_limit_reached")
    if density >= int(limits.get("max_density_repairs", 1)):
        flags.append("density_repair_limit_reached")
    if variants >= int(limits.get("max_training_preset_variants", 1)):
        flags.append("training_variant_limit_reached")

    if all(flag in flags for flag in [
        "exact_confident_repair_limit_reached",
        "density_repair_limit_reached",
        "training_variant_limit_reached",
    ]):
        flags.append("stop_per_npc_loop")
        action = "escalate_shared_strategy"
    else:
        density_decision = density_repair_needed(feedback_data)
        action = "run_density_repair" if density_decision["needed"] and "density_repair_limit_reached" not in flags else "continue_bounded_repair"

    return {
        "npc_key": feedback_data.get("npc_key"),
        "profile": profile,
        "action": action,
        "flags": flags,
        "counts": {
            "exact_confident_failure": exact,
            "density_repair": density,
            "training_preset_variant": variants,
        },
        "limits": limits,
    }


def build_strategy_summary(profile: str = DEFAULT_PROFILE) -> dict[str, Any]:
    strategy = load_strategy_profile(profile)
    return {
        "profile": profile,
        "description": strategy.get("description"),
        "technique": strategy.get("technique"),
        "dataset": strategy.get("dataset"),
        "quality_gate": strategy.get("quality_gate"),
        "training": strategy.get("training"),
        "runtime_eval": strategy.get("runtime_eval"),
        "anti_loop": strategy.get("anti_loop"),
    }


def print_strategy_summary(profile: str = DEFAULT_PROFILE, *, as_json: bool = False) -> None:
    summary = build_strategy_summary(profile)
    if as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return
    print(f"Profile: {summary['profile']}")
    print(f"Description: {summary.get('description')}")
    print(f"Technique: {summary.get('technique')}")
    print(f"Dataset target: {(summary.get('dataset') or {}).get('target_total_rows')}")
    gate = summary.get("quality_gate") or {}
    print(f"Quality gate: {gate.get('mode')} / {gate.get('judge_provider')} / cases={gate.get('cases_per_category')}")
    train = summary.get("training") or {}
    print(f"Training: {train.get('preset')} r{train.get('lora_r')} alpha{train.get('lora_alpha')} seq={train.get('max_seq_len')}")
    runtime = summary.get("runtime_eval") or {}
    print(f"Runtime eval: base_model_required={runtime.get('requires_base_model')} report_html={runtime.get('report_html')}")
    print(f"Anti-loop: {summary.get('anti_loop')}")
