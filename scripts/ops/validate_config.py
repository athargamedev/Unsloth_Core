#!/usr/bin/env python3
"""
validate_config.py — Resolve and validate effective training config without running training.

Usage:
  python scripts/ops/validate_config.py --spec subjects/NPC_specs/chemistry_instructor.json --preset fast-3b --data subjects/datasets/chemistry_instructor/template/train.jsonl
  python scripts/ops/validate_config.py --config configs/lora-sft-base.yaml --preset quality-1.7b
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from scripts._repo_root import PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from scripts.train import load_config, get_available_presets


def _is_canonical_dataset_path(path_str: str) -> bool:
    p = Path(path_str)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    try:
        rel = p.relative_to(paths.dataset_root().resolve())
    except Exception:
        return False
    parts = rel.parts
    return len(parts) >= 3 and parts[2] in {"train.jsonl", "train_clean.jsonl"}


def _extract_dataset_info(path_str: str):
    p = Path(path_str)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    try:
        rel = p.relative_to(paths.dataset_root().resolve())
        parts = rel.parts
        if len(parts) >= 3:
            return parts[0], parts[1], parts[2]
    except Exception:
        pass
    return None, None, None


def validate(args):
    errors = []
    warnings = []

    if args.spec:
        spec_path = Path(args.spec)
        if not spec_path.is_absolute():
            spec_path = PROJECT_ROOT / spec_path
        if not spec_path.exists():
            errors.append(f"Spec not found: {spec_path}")
            return None, errors, warnings
        with open(spec_path) as f:
            spec = json.load(f)
        npc_key = spec.get("npc_key") or spec_path.stem
        config_path = PROJECT_ROOT / "configs" / "lora-sft-base.yaml"  # TODO: use paths.config_root() when available
    else:
        npc_key = args.npc_key
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = PROJECT_ROOT / config_path

    if not config_path.exists():
        errors.append(f"Config not found: {config_path}")
        return None, errors, warnings

    available_presets = get_available_presets()
    if args.preset and args.preset not in available_presets:
        errors.append(f"Unknown preset '{args.preset}'. Available: {', '.join(available_presets)}")

    overrides = {
        "model": args.model,
        "output_dir": args.output,
    }
    config = load_config(str(config_path), preset=args.preset, overrides=overrides)

    model_id = config.get("model", "")
    if "-bnb-4bit" not in model_id:
        warnings.append(f"Model '{model_id}' does not include '-bnb-4bit' suffix (recommended for Unsloth workflow).")
    if "llama" not in model_id.lower():
        warnings.append(
            f"Model '{model_id}' is non-Llama. This project is optimized for Llama-based Unity dialogue deployment."
        )

    # Resolve training data path
    data_path = args.data
    if not data_path and npc_key:
        detected = paths.autodetect_dataset(npc_key)
        if detected:
            _, train_path, _ = detected
            data_path = str(train_path)

    if not data_path:
        warnings.append("No training data path provided and could not auto-detect from npc_key.")
    else:
        if not _is_canonical_dataset_path(data_path):
            msg = f"Non-canonical data path: {data_path} (expected subjects/datasets/{{npc_key}}/{{technique}}/{{train.jsonl|train_clean.jsonl}})"
            if args.require_canonical:
                errors.append(msg)
            else:
                warnings.append(msg)
        d_npc, d_technique, d_file = _extract_dataset_info(data_path)
        if d_npc and npc_key and d_npc != npc_key:
            warnings.append(f"Dataset npc_key '{d_npc}' differs from target npc_key '{npc_key}'.")
        if d_technique and d_technique not in paths.DATASET_TECHNIQUES:
            warnings.append(f"Dataset technique '{d_technique}' is not in {paths.DATASET_TECHNIQUES}.")
        recommended_technique = "docs" if npc_key == "workflow_assistant" else "template"
        if d_technique and d_technique != recommended_technique:
            warnings.append(
                f"Technique '{d_technique}' selected. For production training of '{npc_key}', {recommended_technique} is recommended."
            )
        if d_file and d_file not in {"train.jsonl", "train_clean.jsonl"}:
            warnings.append(f"Dataset file should be train.jsonl or train_clean.jsonl, got {d_file}.")

    raw_output_dir = (
        config.get("training", {}).get("output_dir")
        or config.get("output_dir")
        or str(paths.output_dir(npc_key or "unknown"))
    )
    out_dir = Path(raw_output_dir)
    if not raw_output_dir:
        errors.append("Resolved output_dir is empty.")
    else:
        if not out_dir.is_absolute():
            out_dir = PROJECT_ROOT / out_dir
        try:
            out_dir.resolve().relative_to(paths.output_root().resolve())
        except Exception:
            warnings.append(f"Output dir '{out_dir}' is outside project outputs/.")

    resolved = {
        "npc_key": npc_key,
        "config_path": str(config_path),
        "preset": args.preset,
        "data_path": data_path,
        "resolved_config": config,
    }
    return resolved, errors, warnings


def main():
    parser = argparse.ArgumentParser(description="Resolve and validate effective training config.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spec", help="Path to subject spec JSON")
    source.add_argument("--config", help="Path to YAML config")

    parser.add_argument("--preset", choices=get_available_presets() or None, help="Preset override")
    parser.add_argument("--data", help="Training data path")
    parser.add_argument("--model", help="Model ID override")
    parser.add_argument("--output", help="Output dir override")
    parser.add_argument("--npc-key", help="npc_key when using --config directly")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml", help="Output format")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    parser.add_argument("--require-canonical", action="store_true", help="Require canonical dataset train path")

    args = parser.parse_args()

    resolved, errors, warnings = validate(args)

    if resolved:
        if args.format == "json":
            print(json.dumps(resolved, indent=2))
        else:
            print(yaml.dump(resolved, sort_keys=False, default_flow_style=False))

    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"- {w}")

    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"- {e}")

    if errors or (args.strict and warnings):
        sys.exit(1)

    print("Validation passed.")


if __name__ == "__main__":
    main()
