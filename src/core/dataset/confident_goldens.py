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
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.config import paths
from src.config.logger import setup_logger

logger = setup_logger(__name__)


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


def build_aliases(npc_key: str, technique: str) -> dict[str, str]:
    npc_slug = _slug(npc_key.replace("_", "-"))
    tech_slug = _slug(technique)
    return {
        "single_turn": f"ucore-{npc_slug}-{tech_slug}-single-v1",
        "conversational": f"ucore-{npc_slug}-{tech_slug}-conversation-v1",
    }


def _classifier_hints(metadata: dict[str, Any], text: str, turn_type: str) -> dict[str, str]:
    """Best-effort Confident classifier hints for custom columns.

    These are not classifier outputs. They seed searchable columns and manual review queues
    while Confident's LLM classifiers generate official Signals after ingestion.
    """
    category = str(metadata.get("category") or "").lower()
    concept = str(metadata.get("concept") or "").lower()
    f"{category} {concept} {text}".lower()
    quality = metadata.get("quality_score")

    if turn_type == "conversational":
        return {
            "classifier_expected_failure_mode": "Memory Retention Risk",
            "classifier_repair_priority": "P1 Training Harmful",
            "classifier_strength_hint": "Good Memory Use",
            "classifier_metric_focus": "knowledge_retention",
            "classifier_conversation_weakness_hint": "Lost Context",
            "classifier_expected_strength": "Good Memory Use",
        }

    if "refusal" in category or "safety" in concept or "will not" in concept:
        failure_mode = "Safety Boundary Weakness"
        priority = "P0 Safety/Factual Risk"
    elif isinstance(quality, (int, float)) and quality < 78:
        failure_mode = "Vague / Low Specificity"
        priority = "P1 Training Harmful"
    elif len(text.split()) < 18:
        failure_mode = "Vague / Low Specificity"
        priority = "P1 Training Harmful"
    else:
        failure_mode = "Needs Review"
        priority = "P2 Improve Later"

    if "refusal" in category or "safety" in concept:
        strength = "Good Refusal / Safe Redirect"
    elif priority == "P2 Improve Later":
        strength = "Concrete Teaching"
    else:
        strength = "Needs Review"

    return {
        "classifier_expected_failure_mode": failure_mode,
        "classifier_repair_priority": priority,
        "classifier_strength_hint": strength,
    }


def _infer_npc_technique_from_dataset(
    dataset_path: Path, rows: list[dict[str, Any]] = None
) -> tuple[str, str]:
    npc_key = None
    technique = None
    if rows:
        first_meta = rows[0].get("metadata", {}) or {}
        npc_key = first_meta.get("npc_key")
        technique = first_meta.get("technique")

    parts = dataset_path.parts
    if "datasets" in parts:
        idx = parts.index("datasets")
        if not npc_key and len(parts) > idx + 1:
            npc_key = parts[idx + 1]
        if not technique and len(parts) > idx + 2:
            technique = parts[idx + 2]

    return str(npc_key or "unknown_npc"), str(technique or "unknown")


class ConfidentGoldensConverter:
    """Translates SFT ChatML training rows into Confident-native `Golden` and `ConversationalGolden` projections."""

    def __init__(self, spec: dict[str, Any]):
        self.spec = spec or {}
        if "npc_key" not in self.spec:
            self.spec["npc_key"] = "unknown_npc"
        self.train_clean_path: Path | None = None

    def _extract_context(self, row: dict[str, Any], messages: list[dict[str, Any]]) -> list[str]:
        metadata = row.get("metadata", {}) or {}
        concept = metadata.get("concept", "general")

        # 1. Try reference doc chunks
        ref_doc_val = self.spec.get("reference_doc")
        if ref_doc_val:
            ref_path = Path(ref_doc_val)
            if not ref_path.is_absolute():
                ref_path = paths.PROJECT_ROOT / ref_path
            if ref_path.exists():
                chunks = _reference_context(ref_path)
                if chunks:
                    return chunks

        # 2. Try system rules from messages
        if messages and messages[0].get("role") == "system":
            sys_content = messages[0].get("content", "").strip()
            if sys_content:
                return [sys_content]

        # 3. Fallback to metadata concept
        return [concept]

    def convert_row(self, row: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        messages = row.get("messages", []) or []
        metadata = row.get("metadata", {}) or {}

        # Exactly 3 turns (one system, one user, one assistant)
        is_single = (
            len(messages) == 3
            and messages[0].get("role") == "system"
            and messages[1].get("role") == "user"
            and messages[2].get("role") == "assistant"
        )

        context = self._extract_context(row, messages)
        source_file = str(self.train_clean_path) if self.train_clean_path else "train_clean.jsonl"

        if is_single:
            user_content = messages[1].get("content", "")
            assistant_content = messages[2].get("content", "")

            custom_columns = {
                "npc_key": str(
                    metadata.get("npc_key") or self.spec.get("npc_key") or "unknown_npc"
                ),
                "category": str(metadata.get("category") or "unknown"),
                "concept": str(metadata.get("concept") or "unknown"),
                "difficulty": str(metadata.get("difficulty") or "unknown"),
                "technique": str(metadata.get("technique") or "unknown"),
                "source": str(metadata.get("source") or "unknown"),
                "split": str(metadata.get("split") or "train"),
                "turn_type": "single",
                "quality_status": "candidate",
                **_classifier_hints(metadata, assistant_content, "single"),
            }

            additional = {
                k: v
                for k, v in metadata.items()
                if k
                not in [
                    "npc_key",
                    "category",
                    "concept",
                    "difficulty",
                    "technique",
                    "source",
                    "split",
                ]
            }
            if "system_prompt_hash" not in additional and messages:
                sys_prompt = messages[0].get("content", "")
                additional["system_prompt_hash"] = _sha_text(sys_prompt) if sys_prompt else None
            if "reference_doc_hash" not in additional:
                ref_doc_val = self.spec.get("reference_doc")
                if ref_doc_val:
                    ref_path = Path(ref_doc_val)
                    if not ref_path.is_absolute():
                        ref_path = paths.PROJECT_ROOT / ref_path
                    additional["reference_doc_hash"] = _sha_file(ref_path)
                else:
                    additional["reference_doc_hash"] = None

            golden_dict = {
                "input": user_content,
                "expectedOutput": assistant_content,
                "context": context,
                "comments": "Projected from train_clean.jsonl",
                "sourceFile": source_file,
                "customColumnKeyValues": custom_columns,
                "additionalMetadata": additional,
            }
            return "single", golden_dict

        else:
            scenario = (
                metadata.get("scenario_name")
                or metadata.get("concept")
                or "NPC Conversational Flow"
            )
            user_desc = (
                self.spec.get("relationship_to_player")
                or self.spec.get("player_archetype")
                or "Game player speaking with the NPC"
            )

            assistant_turns = [
                m.get("content", "") for m in messages if m.get("role") == "assistant"
            ]
            last_assistant = assistant_turns[-1] if assistant_turns else ""
            expected_outcome = (
                metadata.get("expected_outcome")
                or last_assistant
                or "Assistant should satisfy the scenario while preserving prior user facts and NPC role constraints."
            )

            turns = [
                {"role": turn["role"], "content": turn["content"]}
                for turn in messages
                if turn["role"] != "system"
            ]

            custom_columns = {
                "npc_key": str(
                    metadata.get("npc_key") or self.spec.get("npc_key") or "unknown_npc"
                ),
                "category": str(metadata.get("category") or "unknown"),
                "concept": str(metadata.get("concept") or "unknown"),
                "difficulty": str(metadata.get("difficulty") or "unknown"),
                "technique": str(metadata.get("technique") or "unknown"),
                "source": str(metadata.get("source") or "unknown"),
                "split": str(metadata.get("split") or "train"),
                "turn_type": "conversational",
                "quality_status": "candidate",
                "metric_focus": "knowledge_retention",
                **_classifier_hints(metadata, "\n".join(assistant_turns), "conversational"),
            }

            additional = {
                k: v
                for k, v in metadata.items()
                if k
                not in [
                    "npc_key",
                    "category",
                    "concept",
                    "difficulty",
                    "technique",
                    "source",
                    "split",
                ]
            }
            if "system_prompt_hash" not in additional and messages:
                sys_prompt = next(
                    (m.get("content", "") for m in messages if m.get("role") == "system"), ""
                )
                additional["system_prompt_hash"] = _sha_text(sys_prompt) if sys_prompt else None
            if "reference_doc_hash" not in additional:
                ref_doc_val = self.spec.get("reference_doc")
                if ref_doc_val:
                    ref_path = Path(ref_doc_val)
                    if not ref_path.is_absolute():
                        ref_path = paths.PROJECT_ROOT / ref_path
                    additional["reference_doc_hash"] = _sha_file(ref_path)
                else:
                    additional["reference_doc_hash"] = None

            golden_dict = {
                "scenario": scenario,
                "userDescription": user_desc,
                "expectedOutcome": expected_outcome,
                "turns": turns,
                "context": context,
                "comments": "Projected from train_clean.jsonl",
                "sourceFile": source_file,
                "additionalMetadata": additional,
                "customColumnKeyValues": custom_columns,
            }
            return "conversational", golden_dict

    def project_dataset(
        self, spec_path: Path, technique: str, output_base: Path = None
    ) -> tuple[Path, Path, Path]:
        if not self.train_clean_path:
            npc_key = self.spec.get("npc_key") or "unknown_npc"

            # Try to load spec from path to recover the actual npc_key
            if (
                (not npc_key or npc_key == "unknown_npc")
                and spec_path
                and spec_path.exists()
                and spec_path.is_file()
            ):
                try:
                    loaded_spec = json.loads(spec_path.read_text(encoding="utf-8"))
                    if loaded_spec.get("npc_key"):
                        npc_key = loaded_spec.get("npc_key")
                        self.spec = loaded_spec
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to load spec from {spec_path}: {e}")

            if not npc_key or npc_key == "unknown_npc":
                raise ValueError("NPC key is missing from subject spec")

            dataset_base = paths.PROJECT_ROOT / "data" / "datasets"
            if not dataset_base.exists():
                dataset_base = paths.dataset_root()

            train_clean_path = dataset_base / npc_key / technique / "train_clean.jsonl"
            if not train_clean_path.exists():
                train_path = dataset_base / npc_key / technique / "train.jsonl"
                if train_path.exists():
                    train_clean_path = train_path
                else:
                    raise FileNotFoundError(
                        f"Neither train_clean.jsonl nor train.jsonl found in {dataset_base / npc_key / technique}"
                    )
            self.train_clean_path = train_clean_path

        rows = _read_jsonl(self.train_clean_path)
        single_goldens = []
        conversational_goldens = []

        for row in rows:
            classification, golden_dict = self.convert_row(row)
            if classification == "single":
                single_goldens.append(golden_dict)
            else:
                conversational_goldens.append(golden_dict)

        if output_base is not None:
            if output_base.name == "confident":
                confident_dir = output_base
            else:
                confident_dir = output_base / "confident"
        else:
            confident_dir = self.train_clean_path.parent / "confident"

        confident_dir.mkdir(parents=True, exist_ok=True)

        single_turn_path = confident_dir / "single_turn_goldens.jsonl"
        conversational_path = confident_dir / "conversational_goldens.jsonl"

        # Preserve manually created or pre-existing conversational goldens if they exist in the target path
        if conversational_path.exists():
            existing_conversational = _read_jsonl(conversational_path)
            seen_scenarios = {
                cg.get("scenario") for cg in conversational_goldens if cg.get("scenario")
            }
            for cg in existing_conversational:
                scenario = cg.get("scenario")
                if not scenario or scenario not in seen_scenarios:
                    conversational_goldens.append(cg)
                    if scenario:
                        seen_scenarios.add(scenario)

        _write_jsonl(single_turn_path, single_goldens)
        _write_jsonl(conversational_path, conversational_goldens)

        dataset_sha = _sha_file(self.train_clean_path) or ""
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        npc_key = self.spec.get("npc_key") or "unknown_npc"
        default_alias = f"ucore-{_slug(npc_key)}-{_slug(technique)}-single-v1"
        default_version = f"{datetime.now(UTC).strftime('%Y%m%d')}-{_short_hash(dataset_sha)}"

        manifest_data = {
            "npc_key": npc_key,
            "technique": technique,
            "dataset_sha": dataset_sha,
            "single_turn_count": len(single_goldens),
            "conversational_count": len(conversational_goldens),
            "created_at": created_at,
            "default_alias": default_alias,
            "default_version": default_version,
            "version": default_version,
            "aliases": {
                "single_turn": f"ucore-{_slug(npc_key)}-{_slug(technique)}-single-v1",
                "conversational": f"ucore-{_slug(npc_key)}-{_slug(technique)}-conversation-v1",
            },
            "counts": {
                "single_turn": len(single_goldens),
                "conversational": len(conversational_goldens),
            },
            "files": {
                "single_turn": str(single_turn_path),
                "conversational": str(conversational_path),
            },
            "push_defaults": {"finalized": False},
        }

        manifest_path = confident_dir / "push_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        return single_turn_path, conversational_path, manifest_path


def project_chatml_rows_to_confident(
    dataset_path: str | Path, spec_path: str | Path | None = None
) -> ConfidentGoldenArtifacts:
    dataset = Path(dataset_path)
    spec, resolved_spec_path = _load_spec(Path(spec_path) if spec_path else None)

    rows = _read_jsonl(dataset)
    first_meta = rows[0].get("metadata", {}) if rows else {}

    inferred_npc_key = spec.get("npc_key") or first_meta.get("npc_key")
    if not inferred_npc_key:
        parts = dataset.parts
        if "datasets" in parts:
            idx = parts.index("datasets")
            if len(parts) > idx + 1:
                inferred_npc_key = parts[idx + 1]
    if not inferred_npc_key:
        inferred_npc_key = "unknown_npc"

    if "npc_key" not in spec or spec["npc_key"] == "unknown_npc":
        spec["npc_key"] = inferred_npc_key

    converter = ConfidentGoldensConverter(spec)
    converter.train_clean_path = dataset

    single_goldens = []
    conversational_goldens = []

    for row in rows:
        classification, golden_dict = converter.convert_row(row)
        if classification == "single":
            single_goldens.append(golden_dict)
        else:
            conversational_goldens.append(golden_dict)

    technique = first_meta.get("technique") or dataset.parent.name or "unknown"
    aliases = build_aliases(inferred_npc_key, technique)

    dataset_hash = _sha_file(dataset) or ""
    spec_hash = _sha_file(resolved_spec_path) or ""

    ref_doc_val = spec.get("reference_doc")
    ref_hash = ""
    if ref_doc_val:
        ref_path = Path(ref_doc_val)
        if not ref_path.is_absolute():
            ref_path = paths.PROJECT_ROOT / ref_path
        ref_hash = _sha_file(ref_path) or ""

    version = f"{datetime.now(UTC).strftime('%Y%m%d')}-{_short_hash(dataset_hash)}-{_short_hash(spec_hash)}-{_short_hash(ref_hash)}"

    return ConfidentGoldenArtifacts(single_goldens, conversational_goldens, aliases, version)


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def build_confident_artifacts(
    dataset_path: str | Path,
    spec_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    technique: str | None = None,
) -> dict[str, Any]:
    dataset_str = str(dataset_path)
    if dataset_str.endswith(".json"):
        if not technique:
            raise ValueError(
                "--technique must be specified when using a subject spec JSON path as the dataset argument."
            )

        spec, resolved_spec_path = _load_spec(Path(dataset_path))
        npc_key = spec.get("npc_key")
        if not npc_key:
            raise ValueError(f"NPC key is missing from subject spec at {dataset_path}")

        dataset_base = paths.PROJECT_ROOT / "data" / "datasets"
        if not dataset_base.exists():
            dataset_base = paths.dataset_root()

        resolved_dataset_path = dataset_base / npc_key / technique / "train_clean.jsonl"
        if not resolved_dataset_path.exists():
            fallback_path = dataset_base / npc_key / technique / "train.jsonl"
            if fallback_path.exists():
                resolved_dataset_path = fallback_path
            else:
                raise FileNotFoundError(
                    f"Neither train_clean.jsonl nor train.jsonl found in {dataset_base / npc_key / technique}"
                )

        spec_path = dataset_path
        dataset_path = resolved_dataset_path

    dataset = Path(dataset_path)
    spec, resolved_spec_path = _load_spec(Path(spec_path) if spec_path else None)

    rows = _read_jsonl(dataset)
    first_meta = rows[0].get("metadata", {}) if rows else {}

    inferred_npc_key = spec.get("npc_key") or first_meta.get("npc_key")
    if not inferred_npc_key:
        parts = dataset.parts
        if "datasets" in parts:
            idx = parts.index("datasets")
            if len(parts) > idx + 1:
                inferred_npc_key = parts[idx + 1]
    if not inferred_npc_key:
        inferred_npc_key = "unknown_npc"

    resolved_technique = (
        technique or first_meta.get("technique") or dataset.parent.name or "unknown"
    )

    if "npc_key" not in spec or spec["npc_key"] == "unknown_npc":
        spec["npc_key"] = inferred_npc_key

    converter = ConfidentGoldensConverter(spec)
    converter.train_clean_path = dataset

    # Resolve output directory
    out_dir = Path(output_dir) if output_dir else dataset.parent / "confident"

    single_turn_path, conversational_path, manifest_path = converter.project_dataset(
        spec_path=resolved_spec_path or Path(), technique=resolved_technique, output_base=out_dir
    )

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Project ChatML dataset rows to Confident AI goldens"
    )
    parser.add_argument(
        "dataset", help="Path to train_clean.jsonl or other ChatML JSONL or NPC spec JSON"
    )
    parser.add_argument("--spec", help="NPC spec JSON for reference_doc/context/provenance")
    parser.add_argument(
        "--output-dir", help="Output directory (default: dataset sibling confident/)"
    )
    parser.add_argument(
        "--technique",
        choices=["docs", "ollama", "template", "openai", "anthropic"],
        help="Generation technique to resolve spec-based projection or metadata fallback",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push projected goldens to Confident AI",
    )
    final_group = parser.add_mutually_exclusive_group()
    final_group.add_argument(
        "--finalized",
        dest="finalized",
        action="store_true",
        default=True,
        help="Mark pushed goldens finalized/eval-ready",
    )
    final_group.add_argument(
        "--unfinalized",
        dest="finalized",
        action="store_false",
        help="Queue pushed goldens for Confident review",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        manifest = build_confident_artifacts(
            args.dataset,
            spec_path=args.spec,
            output_dir=args.output_dir,
            technique=args.technique,
        )
    except (ValueError, FileNotFoundError, json.JSONDecodeError) as exc:
        logger.error(f"Error during projection: {exc}")
        sys.exit(1)
    except Exception:
        logger.exception("Unexpected error during projection")
        sys.exit(1)

    print(json.dumps(manifest, indent=2, ensure_ascii=False))

    if args.push:
        from src.core.ops.confident_push import push_goldens_if_confident

        # Get values from manifest
        version = manifest.get("version") or manifest.get("default_version")

        counts = manifest.get("counts", {})
        single_count = counts.get("single_turn", 0)
        conv_count = counts.get("conversational", 0)

        files = manifest.get("files", {})
        single_file = files.get("single_turn")
        conv_file = files.get("conversational")

        aliases = manifest.get("aliases", {})
        single_alias = aliases.get("single_turn")
        conv_alias = aliases.get("conversational")

        if single_count > 0:
            if not single_file:
                print("Error: Single-turn goldens file path missing from manifest.")
                sys.exit(1)
            ok = push_goldens_if_confident(
                single_file,
                alias=single_alias,
                version=version,
                finalized=args.finalized,
                turn_type="single",
            )
            if not ok:
                print("Error: Single-turn goldens push failed.")
                sys.exit(1)

        if conv_count > 0:
            if not conv_file:
                print("Error: Conversational goldens file path missing from manifest.")
                sys.exit(1)
            ok = push_goldens_if_confident(
                conv_file,
                alias=conv_alias,
                version=version,
                finalized=args.finalized,
                turn_type="conversation",
            )
            if not ok:
                print("Error: Conversational goldens push failed.")
                sys.exit(1)


if __name__ == "__main__":
    main()
