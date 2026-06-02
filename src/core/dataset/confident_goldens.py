#!/usr/bin/env python3
"""Project ChatML NPC training rows into Confident AI golden datasets.

ChatML JSONL remains the SFT training artifact. This module writes Confident-native
single-turn `Golden` and multi-turn `ConversationalGolden` JSONL projections for
Confident dataset review, regression, and remote evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import paths


@dataclass
class ConfidentGoldenArtifacts:
    single_turn_goldens: list[dict[str, Any]] = field(default_factory=list)
    conversational_goldens: list[dict[str, Any]] = field(default_factory=list)
    aliases: dict[str, str] = field(default_factory=dict)
    version: str | None = None
    output_dir: Path | None = None


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path: Path | None) -> str | None:
    if not path or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _short_hash(value: str | None) -> str:
    return (value or "missing")[:8]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"Invalid JSONL at {path}:{line_no}: row must be an object")
        rows.append(parsed)
    return rows


def _load_spec(spec_path: Path | None) -> tuple[dict[str, Any], Path | None]:
    if spec_path is None:
        return {}, None
    resolved = spec_path if spec_path.is_absolute() else paths.PROJECT_ROOT / spec_path
    if not resolved.exists():
        return {}, resolved
    return json.loads(resolved.read_text(encoding="utf-8")), resolved


def _resolve_reference_doc(spec: dict[str, Any], spec_path: Path | None) -> Path | None:
    ref = spec.get("reference_doc")
    if not isinstance(ref, str) or not ref.strip():
        return None
    candidate = Path(ref)
    if candidate.is_absolute():
        return candidate
    if (paths.PROJECT_ROOT / candidate).exists():
        return paths.PROJECT_ROOT / candidate
    if spec_path and (spec_path.parent / candidate).exists():
        return spec_path.parent / candidate
    return paths.PROJECT_ROOT / candidate


def _reference_context(ref_path: Path | None, limit_chars: int = 1400) -> list[str]:
    if not ref_path or not ref_path.exists():
        return []
    text = ref_path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("## ") and current:
            chunk = "\n".join(current).strip()
            if chunk:
                chunks.append(chunk[:limit_chars])
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip()[:limit_chars])
    return [chunk for chunk in chunks[:3] if chunk]


def _infer_npc_technique(dataset_path: Path, rows: list[dict[str, Any]], spec: dict[str, Any]) -> tuple[str, str]:
    first_meta = rows[0].get("metadata", {}) if rows else {}
    npc_key = spec.get("npc_key") or first_meta.get("npc_key")
    technique = first_meta.get("technique")
    try:
        rel = dataset_path.resolve().relative_to(paths.dataset_root().resolve())
        if not npc_key and len(rel.parts) >= 1:
            npc_key = rel.parts[0]
        if not technique and len(rel.parts) >= 2:
            technique = rel.parts[1]
    except Exception:
        pass
    return str(npc_key or "unknown_npc"), str(technique or dataset_path.parent.name or "unknown")


def _messages_by_role(messages: list[dict[str, Any]], role: str) -> list[str]:
    return [str(m.get("content", "")).strip() for m in messages if m.get("role") == role and str(m.get("content", "")).strip()]


def _base_metadata(
    row: dict[str, Any],
    dataset_path: Path,
    spec_path: Path | None,
    ref_path: Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
    messages = row.get("messages", []) if isinstance(row.get("messages"), list) else []
    system_prompt = next((str(m.get("content", "")) for m in messages if m.get("role") == "system"), "")
    ref_hash = _sha_file(ref_path)
    additional = {
        "npc_key": metadata.get("npc_key"),
        "technique": metadata.get("technique"),
        "content_hash": metadata.get("content_hash"),
        "system_prompt_hash": _sha_text(system_prompt) if system_prompt else None,
        "reference_doc": str(ref_path) if ref_path else metadata.get("generator_params", {}).get("reference_doc"),
        "reference_doc_hash": ref_hash,
        "generator": metadata.get("source"),
        "generator_params": metadata.get("generator_params", {}),
        "split": metadata.get("split", "train"),
        "source_dataset": str(dataset_path),
        "spec_path": str(spec_path) if spec_path else None,
    }
    custom = {
        "npc_key": str(metadata.get("npc_key") or "unknown_npc"),
        "category": str(metadata.get("category") or "unknown"),
        "concept": str(metadata.get("concept") or "unknown"),
        "difficulty": str(metadata.get("difficulty") or "unknown"),
        "technique": str(metadata.get("technique") or "unknown"),
        "source": str(metadata.get("source") or "unknown"),
        "split": str(metadata.get("split") or "train"),
        "quality_status": "candidate",
    }
    return additional, custom


def _single_turn_golden(row: dict[str, Any], dataset_path: Path, spec_path: Path | None, ref_path: Path | None, context: list[str]) -> dict[str, Any] | None:
    messages = row.get("messages", []) if isinstance(row.get("messages"), list) else []
    user_messages = _messages_by_role(messages, "user")
    assistant_messages = _messages_by_role(messages, "assistant")
    if not user_messages or not assistant_messages:
        return None
    additional, custom = _base_metadata(row, dataset_path, spec_path, ref_path)
    custom["turn_type"] = "single"
    return {
        "input": user_messages[-1],
        "expectedOutput": assistant_messages[-1],
        "context": context,
        "comments": "Projected from ChatML train_clean.jsonl for Confident AI review/regression; runtime eval should fill actualOutput.",
        "sourceFile": str(dataset_path),
        "additionalMetadata": additional,
        "customColumnKeyValues": custom,
    }


def _conversational_golden(row: dict[str, Any], dataset_path: Path, spec_path: Path | None, ref_path: Path | None, context: list[str]) -> dict[str, Any] | None:
    messages = row.get("messages", []) if isinstance(row.get("messages"), list) else []
    user_messages = _messages_by_role(messages, "user")
    assistant_messages = _messages_by_role(messages, "assistant")
    if not user_messages:
        return None
    additional, custom = _base_metadata(row, dataset_path, spec_path, ref_path)
    custom["turn_type"] = "multi"
    custom["metric_focus"] = "knowledge_retention"
    npc_key = custom["npc_key"]
    category = custom["category"]
    concept = custom["concept"]
    scenario = f"{npc_key} {category} conversation about {concept}"
    expected = assistant_messages[-1] if assistant_messages else "Assistant should satisfy the scenario while preserving prior user facts and NPC role constraints."
    return {
        "scenario": scenario,
        "userDescription": "Game player speaking with the NPC; may provide facts, preferences, constraints, or goals that should persist across turns.",
        "expectedOutcome": expected,
        "turns": [{"role": "user", "content": user_messages[0]}],
        "context": context,
        "comments": "Projected as ConversationalGolden. Opening user turn is kept; runtime eval should generate/score the full conversation.",
        "sourceFile": str(dataset_path),
        "additionalMetadata": additional,
        "customColumnKeyValues": custom,
    }


def build_aliases(npc_key: str, technique: str) -> dict[str, str]:
    npc_slug = _slug(npc_key.replace("_", "-"))
    tech_slug = _slug(technique)
    return {
        "single_turn": f"ucore-{npc_slug}-{tech_slug}-single-v1",
        "conversational": f"ucore-{npc_slug}-{tech_slug}-conversation-v1",
    }


def project_chatml_rows_to_confident(dataset_path: str | Path, spec_path: str | Path | None = None) -> ConfidentGoldenArtifacts:
    dataset = Path(dataset_path)
    spec, resolved_spec_path = _load_spec(Path(spec_path) if spec_path else None)
    ref_path = _resolve_reference_doc(spec, resolved_spec_path)
    rows = _read_jsonl(dataset)
    npc_key, technique = _infer_npc_technique(dataset, rows, spec)
    context = _reference_context(ref_path)
    single: list[dict[str, Any]] = []
    conversational: list[dict[str, Any]] = []
    for row in rows:
        messages = row.get("messages", []) if isinstance(row.get("messages"), list) else []
        non_system = [m for m in messages if m.get("role") != "system"]
        if len(non_system) > 2:
            golden = _conversational_golden(row, dataset, resolved_spec_path, ref_path, context)
            if golden:
                conversational.append(golden)
        else:
            golden = _single_turn_golden(row, dataset, resolved_spec_path, ref_path, context)
            if golden:
                single.append(golden)
    version = None
    dataset_hash = _sha_file(dataset)
    spec_hash = _sha_file(resolved_spec_path)
    ref_hash = _sha_file(ref_path)
    if dataset_hash:
        version = f"{datetime.now(timezone.utc).strftime('%Y%m%d')}-{_short_hash(dataset_hash)}-{_short_hash(spec_hash)}-{_short_hash(ref_hash)}"
    return ConfidentGoldenArtifacts(single, conversational, build_aliases(npc_key, technique), version)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def build_confident_artifacts(dataset_path: str | Path, spec_path: str | Path | None = None, output_dir: str | Path | None = None) -> dict[str, Any]:
    dataset = Path(dataset_path)
    artifacts = project_chatml_rows_to_confident(dataset, spec_path=spec_path)
    out_dir = Path(output_dir) if output_dir else dataset.parent / "confident"
    _write_jsonl(out_dir / "single_turn_goldens.jsonl", artifacts.single_turn_goldens)
    _write_jsonl(out_dir / "conversational_goldens.jsonl", artifacts.conversational_goldens)
    manifest = {
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_dataset": str(dataset),
        "spec_path": str(spec_path) if spec_path else None,
        "version": artifacts.version,
        "aliases": artifacts.aliases,
        "counts": {
            "single_turn": len(artifacts.single_turn_goldens),
            "conversational": len(artifacts.conversational_goldens),
        },
        "files": {
            "single_turn": str(out_dir / "single_turn_goldens.jsonl"),
            "conversational": str(out_dir / "conversational_goldens.jsonl"),
        },
        "push_defaults": {"finalized": False},
    }
    (out_dir / "push_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Project ChatML dataset rows to Confident AI goldens")
    parser.add_argument("dataset", help="Path to train_clean.jsonl or other ChatML JSONL")
    parser.add_argument("--spec", help="NPC spec JSON for reference_doc/context/provenance")
    parser.add_argument("--output-dir", help="Output directory (default: dataset sibling confident/)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    manifest = build_confident_artifacts(args.dataset, spec_path=args.spec, output_dir=args.output_dir)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
