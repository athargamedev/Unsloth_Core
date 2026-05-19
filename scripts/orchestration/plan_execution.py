#!/usr/bin/env python3
"""
plan_execution.py

Compute a deterministic recommendation for where to run:
- dataset generation: local vs remote
- training: local vs remote_colab

Usage:
  python scripts/plan_execution.py --spec subjects/NPC_specs/chemistry_instructor.json --preset fast-3b --json
  python scripts/plan_execution.py --spec subjects/NPC_specs/chemistry_instructor.json --preset llama-3b-fast --local-vram-gb 6
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from scripts._repo_root import PROJECT_ROOT
PRESETS_DIR = PROJECT_ROOT / "configs" / "presets"
BASE_CONFIG_PATH = PROJECT_ROOT / "configs" / "lora-sft-base.yaml"
POLICY_PATH = PROJECT_ROOT / "configs" / "workload-policy.yaml"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def parse_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def detect_local_vram_gb() -> float | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        if not out:
            return None
        values = [float(line.strip()) for line in out.splitlines() if line.strip()]
        if not values:
            return None
        # Multi-GPU: use largest card for single-run planning.
        return round(max(values) / 1024.0, 1)
    except Exception:
        return None


def infer_model_bucket(model_name: str) -> str:
    m = model_name.lower()
    if "8b" in m:
        return "8b"
    if "7b" in m:
        return "7b"
    if "3b" in m:
        return "3b"
    if "1.7b" in m:
        return "1.7b"
    if "1b" in m:
        return "1b"
    if "0.5b" in m:
        return "0.5b"
    return "3b"


def estimate_training_vram_gb(config: dict[str, Any], policy: dict[str, Any]) -> float:
    model = str(config.get("model", ""))
    training = config.get("training", {})
    lora = config.get("lora", {})

    bucket = infer_model_bucket(model)
    baseline = float(policy.get("model_vram_baseline_gb", {}).get(bucket, 8.0))

    lora_r = float(lora.get("r", lora.get("lora_r", 16)))
    max_seq = float(training.get("max_seq_length", 2048))
    packing = bool(training.get("packing", True))

    estimated = baseline
    estimated += (lora_r - 16) * 0.1
    estimated *= max_seq / 2048.0
    if packing:
        estimated *= 0.85

    return round(estimated, 1)


def load_resolved_config(spec: dict[str, Any], preset_name: str | None) -> dict[str, Any]:
    base = parse_yaml(BASE_CONFIG_PATH)

    # Spec-derived defaults
    technique = spec.get("technique") or spec.get("dataset", {}).get("technique") or "template"
    model_id = (
        spec.get("model")
        or spec.get("model_id")
        or spec.get("llm", {}).get("model_name")
        or spec.get("llm", {}).get("base_model")
        or base.get("model")
    )

    resolved = deep_merge(base, {"model": model_id, "dataset": {"technique": technique}})

    if preset_name:
        preset_path = PRESETS_DIR / f"{preset_name}.yaml"
        if not preset_path.exists():
            raise ValueError(f"Unknown preset: {preset_name}")
        resolved = deep_merge(resolved, parse_yaml(preset_path))

    return resolved


def sum_examples(spec: dict[str, Any]) -> int:
    cats = spec.get("dataset", {}).get("examples_per_category", {})
    if not isinstance(cats, dict):
        return 0
    total = 0
    for v in cats.values():
        try:
            total += int(v)
        except Exception:
            pass
    return total


def recommend(spec: dict[str, Any], preset: str | None, local_vram_gb: float | None) -> dict[str, Any]:
    policy = parse_yaml(POLICY_PATH)
    config = load_resolved_config(spec, preset)

    technique = str(config.get("dataset", {}).get("technique", "template"))
    examples = sum_examples(spec)

    # Dataset generation decision
    gen_location = "local"
    gen_reason = "Default local orchestration"

    ollama_min = float(policy.get("local_caps", {}).get("ollama_min_vram_gb", 6))

    if technique == "ollama" and local_vram_gb is not None and local_vram_gb < ollama_min:
        gen_location = "remote"
        gen_reason = f"Ollama generation needs >= {ollama_min}GB VRAM, local has {local_vram_gb}GB"

    # Training decision
    est_vram = estimate_training_vram_gb(config, policy)
    margin = float(policy.get("safety", {}).get("training_vram_safety_margin", 1.25))
    required = round(est_vram * margin, 1)

    training_location = "remote_colab"
    training_reason = f"No local VRAM detected; required ~{required}GB with safety margin"
    if local_vram_gb is not None:
        if local_vram_gb >= required:
            training_location = "local"
            training_reason = f"Local VRAM {local_vram_gb}GB >= required {required}GB"
        else:
            training_location = "remote_colab"
            training_reason = f"Local VRAM {local_vram_gb}GB < required {required}GB"

    return {
        "npc_key": spec.get("npc_key"),
        "preset": preset,
        "technique": technique,
        "dataset_examples_total": examples,
        "local_vram_gb": local_vram_gb,
        "estimated_training_vram_gb": est_vram,
        "required_training_vram_with_margin_gb": required,
        "recommendation": {
            "dataset_generation": {"location": gen_location, "reason": gen_reason},
            "training": {"location": training_location, "reason": training_reason},
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Plan local vs remote execution for dataset generation + training")
    ap.add_argument("--spec", required=True, help="Path to subject spec JSON")
    ap.add_argument("--preset", help="Preset name from configs/presets")
    ap.add_argument("--local-vram-gb", type=float, help="Override local VRAM GB (if omitted, auto-detect nvidia-smi)")
    ap.add_argument("--json", action="store_true", help="Print JSON only")
    args = ap.parse_args()

    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = (PROJECT_ROOT / spec_path).resolve()
    if not spec_path.exists():
        raise SystemExit(f"Spec not found: {spec_path}")

    spec = parse_json(spec_path)
    local_vram = args.local_vram_gb if args.local_vram_gb is not None else detect_local_vram_gb()

    plan = recommend(spec, args.preset, local_vram)

    if args.json:
        print(json.dumps(plan, indent=2))
        return 0

    print("Execution Planning")
    print(f"  NPC:                 {plan.get('npc_key')}")
    print(f"  Preset:              {plan.get('preset') or 'none'}")
    print(f"  Technique:           {plan.get('technique')}")
    print(f"  Dataset examples:    {plan.get('dataset_examples_total')}")
    print(f"  Local VRAM:          {plan.get('local_vram_gb')}")
    print(f"  Est. train VRAM:     {plan.get('estimated_training_vram_gb')} GB")
    print(f"  Required (+margin):  {plan.get('required_training_vram_with_margin_gb')} GB")

    gen = plan["recommendation"]["dataset_generation"]
    trn = plan["recommendation"]["training"]
    print(f"  Dataset generation:  {gen['location']}  ({gen['reason']})")
    print(f"  Training:            {trn['location']}  ({trn['reason']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
