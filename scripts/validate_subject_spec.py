#!/usr/bin/env python3
"""Validate subject specs before dataset generation or training."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config.paths import SNAKE_CASE_PATTERN

GENERATOR_SUPPORTED_DATASET_CATEGORIES = {"identity", "teaching", "dialogue", "quest", "refusal"}


@dataclass(frozen=True)
class SpecResult:
    path: str
    npc_key: str | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.errors:
            return "error"
        if self.warnings:
            return "warning"
        return "ok"

    def to_json_object(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "npc_key": self.npc_key,
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def project_relative_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def normalized_display_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value)


def read_json_object(spec_path: Path) -> tuple[dict[str, Any] | None, list[str]]:
    if not spec_path.exists():
        return None, [f"Spec not found: {spec_path}"]

    try:
        parsed = json.loads(spec_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return None, [f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"]
    except OSError as exc:
        return None, [f"Could not read spec: {exc}"]

    if not isinstance(parsed, dict):
        return None, ["Spec root must be a JSON object."]

    return parsed, []


def require_object(spec: dict[str, Any], field_name: str, errors: list[str]) -> dict[str, Any] | None:
    value = spec.get(field_name)
    if isinstance(value, dict):
        return value

    errors.append(f"Missing or invalid `{field_name}` object.")
    return None


def require_non_empty_string(container: dict[str, Any], field_path: str, errors: list[str]) -> str | None:
    value = container.get(field_path.rsplit(".", 1)[-1])
    if is_non_empty_string(value):
        return value.strip()

    errors.append(f"Missing or invalid `{field_path}` non-empty string.")
    return None


def validate_research_queries(spec: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    research_queries = spec.get("research_queries")
    research_fallback = spec.get("research")

    if research_queries is None and research_fallback is not None:
        research_queries = research_fallback
        warnings.append("Using fallback `research`; prefer `research_queries` for generation readiness.")

    if not is_non_empty_list(research_queries):
        errors.append("Missing or invalid research query array (`research_queries` preferred, `research` fallback allowed).")
        return

    for index, entry in enumerate(research_queries):
        if not isinstance(entry, dict):
            errors.append(f"Research entry {index} must be an object with a non-empty `query` string.")
            continue

        if not is_non_empty_string(entry.get("query")):
            errors.append(f"Research entry {index} is missing a non-empty `query` string.")


def validate_system_prompt(spec: dict[str, Any], npc_name: str | None, max_sentences: int | None, errors: list[str], warnings: list[str]) -> None:
    system_prompt = spec.get("system_prompt")
    if not is_non_empty_string(system_prompt):
        errors.append("Missing or invalid `system_prompt` non-empty string.")
        return

    normalized_prompt = normalized_display_name(system_prompt)
    if npc_name and normalized_display_name(npc_name) not in normalized_prompt:
        warnings.append("`system_prompt` should mention `npc_name` or its normalized display form.")

    if max_sentences is None:
        return

    sentence_limit_patterns = [
        rf"\bmax(?:imum)?\s+{max_sentences}\s+sentences?\b",
        rf"\b1\s*[-–—]\s*{max_sentences}\s+[^.]*sentences?\b",
        rf"\b{max_sentences}\s+[^.]*sentences?\b",
    ]
    if any(re.search(pattern, system_prompt, re.IGNORECASE) for pattern in sentence_limit_patterns):
        return

    warnings.append(f"`system_prompt` should include a sentence limit consistent with dialogue.max_sentences={max_sentences}.")


def validate_dataset(spec: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    dataset = spec.get("dataset")
    if not isinstance(dataset, dict):
        errors.append("Missing or invalid `dataset` object.")
        return

    examples_per_category = dataset.get("examples_per_category")
    if not isinstance(examples_per_category, dict) or not examples_per_category:
        errors.append("Missing or invalid `dataset.examples_per_category` non-empty object.")
        return

    has_positive_supported_category = False

    for category, count in examples_per_category.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"`dataset.examples_per_category.{category}` must be a non-negative integer.")
            continue

        if category in GENERATOR_SUPPORTED_DATASET_CATEGORIES:
            has_positive_supported_category = has_positive_supported_category or count > 0
            continue

        if count > 0:
            errors.append(
                f"Unknown dataset category `{category}` has a positive count but no generator support. "
                f"Supported categories: {', '.join(sorted(GENERATOR_SUPPORTED_DATASET_CATEGORIES))}."
            )
            continue

        warnings.append(f"Unknown zero-count dataset category `{category}` ignored; remove it or add generator support before use.")

    if not has_positive_supported_category:
        errors.append(
            "`dataset.examples_per_category` must request at least one example in a generator-supported category "
            f"({', '.join(sorted(GENERATOR_SUPPORTED_DATASET_CATEGORIES))})."
        )

    quest_count = examples_per_category.get("quest", 0)
    quest = spec.get("quest")
    quest_scenarios = quest.get("scenarios") if isinstance(quest, dict) else None
    if isinstance(quest_count, int) and quest_count > 0 and not is_non_empty_list(quest_scenarios):
        warnings.append("Quest examples are requested, but optional `quest.scenarios` is empty or missing.")


def validate_spec(spec_path: Path) -> SpecResult:
    errors: list[str] = []
    warnings: list[str] = []
    resolved_path = spec_path if spec_path.is_absolute() else PROJECT_ROOT / spec_path
    display_path = project_relative_path(resolved_path)

    spec, read_errors = read_json_object(resolved_path)
    if read_errors:
        return SpecResult(path=display_path, errors=read_errors)
    if spec is None:
        return SpecResult(path=display_path, errors=["Spec could not be parsed."])

    npc_key = spec.get("npc_key")
    if not is_non_empty_string(npc_key):
        errors.append("Missing or invalid `npc_key` non-empty string.")
        npc_key = None
    else:
        npc_key = npc_key.strip()
        if not SNAKE_CASE_PATTERN.fullmatch(npc_key):
            errors.append("`npc_key` must be snake_case (lowercase letters, numbers, and underscores).")
        if resolved_path.stem != npc_key:
            errors.append(f"Filename stem `{resolved_path.stem}` must match npc_key `{npc_key}`.")

    npc_name = spec.get("npc_name")
    if not is_non_empty_string(npc_name):
        errors.append("Missing or invalid `npc_name` non-empty string.")
        npc_name = None
    else:
        npc_name = npc_name.strip()

    if not is_non_empty_string(spec.get("subject")):
        errors.append("Missing or invalid `subject` non-empty string.")

    identity = require_object(spec, "identity", errors)
    if identity is not None:
        require_non_empty_string(identity, "identity.personality", errors)
        require_non_empty_string(identity, "identity.background", errors)
        require_non_empty_string(identity, "identity.mannerisms", errors)

    teaching = require_object(spec, "teaching", errors)
    if teaching is not None:
        if not is_non_empty_list(teaching.get("expertise")):
            errors.append("Missing or invalid `teaching.expertise` non-empty list.")
        require_non_empty_string(teaching, "teaching.approach", errors)

    max_sentences: int | None = None
    dialogue = require_object(spec, "dialogue", errors)
    if dialogue is not None:
        value = dialogue.get("max_sentences")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            max_sentences = value
            if value > 5:
                warnings.append("`dialogue.max_sentences` is greater than 5; short NPC responses are recommended.")
        else:
            errors.append("Missing or invalid `dialogue.max_sentences` positive integer.")
        if not is_non_empty_list(dialogue.get("example_topics")):
            errors.append("Missing or invalid `dialogue.example_topics` non-empty list.")

    refusal = require_object(spec, "refusal", errors)
    if refusal is not None:
        if not is_non_empty_list(refusal.get("boundaries")):
            errors.append("Missing or invalid `refusal.boundaries` non-empty list.")
        require_non_empty_string(refusal, "refusal.redirect_policy", errors)

    validate_research_queries(spec, errors, warnings)
    validate_system_prompt(spec, npc_name, max_sentences, errors, warnings)
    validate_dataset(spec, errors, warnings)

    return SpecResult(path=display_path, npc_key=npc_key, errors=errors, warnings=warnings)


def find_subject_specs() -> list[Path]:
    return sorted((PROJECT_ROOT / "subjects").glob("*.json"))


def print_human_results(results: list[SpecResult]) -> None:
    for result in results:
        label = result.npc_key or "unknown npc_key"
        print(f"{result.path}: {result.status.upper()} ({label})")
        for error in result.errors:
            print(f"  ERROR: {error}")
        for warning in result.warnings:
            print(f"  WARNING: {warning}")

    error_count = sum(len(result.errors) for result in results)
    warning_count = sum(len(result.warnings) for result in results)
    print(f"Summary: {len(results)} spec(s), {error_count} error(s), {warning_count} warning(s).")


def build_json_payload(results: list[SpecResult]) -> dict[str, Any]:
    return {
        "results": [result.to_json_object() for result in results],
        "summary": {
            "specs": len(results),
            "ok": sum(1 for result in results if result.status == "ok"),
            "warnings": sum(len(result.warnings) for result in results),
            "errors": sum(len(result.errors) for result in results),
            "failed_specs": sum(1 for result in results if result.errors),
            "warning_specs": sum(1 for result in results if result.warnings and not result.errors),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate subject specs before generation/training.")
    parser.add_argument("spec", nargs="?", help="Path to one subjects/*.json spec")
    parser.add_argument("--all", action="store_true", help="Validate every subjects/*.json spec")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero on warnings as well as errors")
    args = parser.parse_args()

    if args.all and args.spec:
        parser.error("Provide a spec path or --all, not both.")
    if not args.all and not args.spec:
        parser.error("Provide a spec path or --all.")
    return args


def main() -> None:
    args = parse_args()
    spec_paths = find_subject_specs() if args.all else [Path(args.spec)]
    results = [validate_spec(path) for path in spec_paths]

    if args.json:
        print(json.dumps(build_json_payload(results), indent=2))
    else:
        print_human_results(results)

    has_errors = any(result.errors for result in results)
    has_warnings = any(result.warnings for result in results)
    if has_errors or (args.strict and has_warnings):
        sys.exit(1)


if __name__ == "__main__":
    main()
