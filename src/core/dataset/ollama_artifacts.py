from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import shutil

from src.config.paths import dataset_latest_symlink, dataset_version_dir, generate_version_timestamp
from src.core.dataset.dataset_contracts import calculate_distribution_gaps, dataset_contract_from_spec


def build_ollama_manifest(
    *,
    npc_key: str,
    technique: str,
    model: str,
    spec_path: str,
    spec: dict[str, Any],
    examples: list[dict[str, Any]],
    train_examples: list[dict[str, Any]],
    val_examples: list[dict[str, Any]],
    examples_per_category: dict[str, int],
    generator_stats: dict[str, Any],
    seed: int,
    temperature: float,
    multi_turn_ratio: float,
) -> dict[str, Any]:
    by_category = defaultdict(int)
    by_difficulty = defaultdict(int)
    by_concept = defaultdict(int)
    for ex in examples:
        meta = ex.get("metadata", {})
        by_category[meta.get("category", "unknown")] += 1
        diff = meta.get("difficulty")
        if diff:
            by_difficulty[diff] += 1
        conc = meta.get("concept")
        if conc:
            by_concept[conc] += 1

    dataset_contract = dataset_contract_from_spec(spec)
    spec_hash = None
    try:
        path = Path(spec_path)
        if path.exists():
            spec_hash = "sha256:" + sha256(path.read_bytes()).hexdigest()
    except Exception:
        spec_hash = None

    return {
        "npc_key": npc_key,
        "technique": technique,
        "model": model,
        "generation": {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": seed,
            "temperature": temperature,
            "multi_turn_ratio": multi_turn_ratio,
            "version": "ollama-v2",
        },
        "spec": {"file": str(Path(spec_path).resolve()), "hash": spec_hash},
        "contract": dataset_contract,
        "distribution": {
            "expected_examples_per_category": dataset_contract["expected_examples_per_category"],
            "generation_request_examples_per_category": dict(examples_per_category),
            "observed_examples_per_category": dict(by_category),
            "distribution_gaps": calculate_distribution_gaps(dataset_contract["expected_examples_per_category"], dict(by_category)),
        },
        "statistics": {
            "total": len(examples),
            "train": len(train_examples),
            "validation": len(val_examples),
            "by_category": dict(by_category),
            "by_difficulty": dict(by_difficulty),
            "by_concept": dict(sorted(by_concept.items(), key=lambda x: -x[1])),
            "generator_stats": generator_stats,
        },
    }


def write_ollama_dataset_artifacts(
    *,
    output_path: str | Path,
    train_examples: list[dict[str, Any]],
    val_examples: list[dict[str, Any]],
    manifest: dict[str, Any],
    create_version_copy: bool = True,
) -> dict[str, str | None]:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    val_path = None

    with output_path.open("w", encoding="utf-8") as f:
        for ex in train_examples:
            ex["metadata"]["split"] = "train"
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    if val_examples:
        val_path = output_path.parent / "validation.jsonl"
        with val_path.open("w", encoding="utf-8") as f:
            for ex in val_examples:
                ex["metadata"]["split"] = "validation"
                f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    manifest_path = output_path.parent / "train_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if create_version_copy:
        version = generate_version_timestamp()
        version_dir = dataset_version_dir(manifest["npc_key"], manifest["technique"], version)
        version_dir.mkdir(parents=True, exist_ok=True)
        for src_file in [output_path, val_path, manifest_path]:
            if src_file and Path(src_file).exists():
                shutil.copy2(src_file, version_dir / Path(src_file).name)
        latest_link = dataset_latest_symlink(manifest["npc_key"], manifest["technique"])
        latest_link.parent.mkdir(parents=True, exist_ok=True)
        tmp_link = latest_link.parent / ".latest_tmp"
        try:
            tmp_link.unlink(missing_ok=True)
            tmp_link.symlink_to(version_dir.name)
            tmp_link.rename(latest_link)
        except (OSError, FileNotFoundError):
            pass

    return {"output_path": str(output_path), "val_path": str(val_path) if val_path else None, "manifest_path": str(manifest_path)}
