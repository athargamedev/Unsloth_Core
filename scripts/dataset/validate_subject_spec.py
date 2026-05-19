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


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from _config.paths import SNAKE_CASE_PATTERN
from scripts.dataset_contracts import (
    MIN_DATASET_EXAMPLES_PER_CATEGORY,
    SUPPORTED_DATASET_CATEGORIES,
    VALID_DIFFICULTY_LEVELS,
)

GENERATOR_SUPPORTED_DATASET_CATEGORIES = set(SUPPORTED_DATASET_CATEGORIES)
REFERENCE_DOC_MIN_WORDS = 250
REFERENCE_DOC_MIN_H2_SECTIONS = 5
REFERENCE_DOC_MIN_BULLETS = 20
REFERENCE_DOC_QUALITY_PATTERN = re.compile(r"\b(boundar(?:y|ies)|refusal|safety|misconception|myth)\b", re.IGNORECASE)
PLACEHOLDER_PATTERN = re.compile(r"\b(TODO|TBD|FIXME|stub|placeholder)\b", re.IGNORECASE)


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

    VALID_MODES = {"fast", "deep"}

    for index, entry in enumerate(research_queries):
        if not isinstance(entry, dict):
            errors.append(f"Research entry {index} must be an object with a non-empty `query` string and a `mode` (fast/deep).")
            continue

        if not is_non_empty_string(entry.get("query")):
            errors.append(f"Research entry {index} is missing a non-empty `query` string.")

        mode = entry.get("mode")
        if mode not in VALID_MODES:
            errors.append(f"Research entry {index} has invalid `mode` \"{mode}\"; expected one of: {', '.join(sorted(VALID_MODES))}.")


def validate_reference_docs(
    spec: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    *,
    require_reference_docs: bool = False,
    require_reference_contract: bool = False,
) -> None:
    reference_doc = spec.get("reference_doc")
    if not is_non_empty_string(reference_doc):
        msg = "No `reference_doc` field; add a reference primer for grounded dataset generation."
        if require_reference_docs or require_reference_contract:
            errors.append(msg)
        else:
            warnings.append(msg)
        return

    doc_path = PROJECT_ROOT / reference_doc
    if not doc_path.exists():
        msg = f"`reference_doc` file not found: {reference_doc}"
        if require_reference_docs:
            errors.append(msg)
        else:
            warnings.append(msg)
        return

    try:
        text = doc_path.read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"Could not read `reference_doc` {reference_doc}: {exc}")
        return

    contract_errors: list[str] = []
    contract_warnings: list[str] = []

    if not str(reference_doc).startswith("subjects/reference_docs/"):
        contract_errors.append("`reference_doc` must live under subjects/reference_docs/.")

    if doc_path.suffix.lower() != ".md":
        contract_errors.append("`reference_doc` must be a Markdown file.")

    if not re.search(r"^#\s+\S+", text, re.MULTILINE):
        contract_errors.append("Reference doc must start with one H1 title.")

    h2_count = len(re.findall(r"^##\s+\S+", text, re.MULTILINE))
    if h2_count < REFERENCE_DOC_MIN_H2_SECTIONS:
        contract_errors.append(
            f"Reference doc must have at least {REFERENCE_DOC_MIN_H2_SECTIONS} H2 sections; found {h2_count}."
        )

    bullet_count = len(re.findall(r"^\s*(?:[-*]|\d+\.)\s+\S+", text, re.MULTILINE))
    if bullet_count < REFERENCE_DOC_MIN_BULLETS:
        contract_errors.append(
            f"Reference doc must have at least {REFERENCE_DOC_MIN_BULLETS} concrete bullets; found {bullet_count}."
        )

    word_count = len(re.findall(r"\b[\w'-]+\b", text))
    if word_count < REFERENCE_DOC_MIN_WORDS:
        contract_errors.append(
            f"Reference doc must have at least {REFERENCE_DOC_MIN_WORDS} words; found {word_count}."
        )

    if PLACEHOLDER_PATTERN.search(text):
        contract_errors.append("Reference doc contains placeholder/TODO language.")

    if not REFERENCE_DOC_QUALITY_PATTERN.search(text):
        contract_warnings.append(
            "Reference doc should include safety, refusal, boundary, or misconception notes for better refusal/dialogue data."
        )

    if require_reference_contract:
        errors.extend(f"`reference_doc` contract: {msg}" for msg in contract_errors)
        errors.extend(f"`reference_doc` contract: {msg}" for msg in contract_warnings)
    else:
        warnings.extend(f"`reference_doc` contract: {msg}" for msg in contract_errors)
        warnings.extend(f"`reference_doc` contract: {msg}" for msg in contract_warnings)


def validate_difficulty_levels(spec: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    teaching = spec.get("teaching")
    if not isinstance(teaching, dict):
        return

    levels = teaching.get("difficulty_levels")
    if levels is None:
        warnings.append(
            "Missing `teaching.difficulty_levels`; it should be a list of allowed levels or a concept-to-level mapping."
        )
        return

    if isinstance(levels, list):
        if not levels:
            warnings.append("`teaching.difficulty_levels` should contain at least one difficulty level.")
            return
        for level in levels:
            if not is_non_empty_string(level) or level not in VALID_DIFFICULTY_LEVELS:
                warnings.append(
                    f"`teaching.difficulty_levels` contains invalid level `{level}`; valid values are: {', '.join(sorted(VALID_DIFFICULTY_LEVELS))}."
                )
    elif isinstance(levels, dict):
        if not levels:
            warnings.append("`teaching.difficulty_levels` mapping should contain at least one concept-to-level entry.")
            return
        for key, value in levels.items():
            if not is_non_empty_string(key):
                errors.append("`teaching.difficulty_levels` mapping keys must be non-empty strings.")
            if not is_non_empty_string(value) or value not in VALID_DIFFICULTY_LEVELS:
                errors.append(
                    f"`teaching.difficulty_levels['{key}']` must be one of: {', '.join(sorted(VALID_DIFFICULTY_LEVELS))}."
                )
    else:
        errors.append("`teaching.difficulty_levels` must be either a list of levels or a mapping from concept to level.")


def validate_concepts(spec: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    concepts = spec.get("concepts")
    if concepts is None:
        return

    if not isinstance(concepts, list):
        errors.append("`concepts` must be an array if present.")
        return

    for index, item in enumerate(concepts):
        if isinstance(item, str):
            if not item.strip():
                errors.append(f"`concepts[{index}]` must be a non-empty string.")
            continue

        if not isinstance(item, dict):
            errors.append(f"`concepts[{index}]` must be either a string or an object.")
            continue

        if not is_non_empty_string(item.get("name")):
            errors.append(f"Missing or invalid `concepts[{index}].name` non-empty string.")

        difficulty = item.get("difficulty")
        if difficulty is not None and difficulty not in VALID_DIFFICULTY_LEVELS:
            errors.append(
                f"`concepts[{index}].difficulty` must be one of: {', '.join(sorted(VALID_DIFFICULTY_LEVELS))}."
            )

        category = item.get("category")
        if category is not None and not isinstance(category, str):
            errors.append(f"`concepts[{index}].category` must be a string if present.")
        elif isinstance(category, str) and category not in GENERATOR_SUPPORTED_DATASET_CATEGORIES:
            warnings.append(
                f"`concepts[{index}].category` is not a supported dataset category; supported values are: {', '.join(sorted(GENERATOR_SUPPORTED_DATASET_CATEGORIES))}."
            )

        aliases = item.get("aliases")
        if aliases is not None and not isinstance(aliases, list):
            errors.append(f"`concepts[{index}].aliases` must be a list of strings if present.")
        elif isinstance(aliases, list):
            for alias in aliases:
                if not is_non_empty_string(alias):
                    errors.append(f"`concepts[{index}].aliases` must contain only non-empty strings.")
                    break


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


def validate_dataset(
    spec: dict[str, Any],
    errors: list[str],
    warnings: list[str],
    *,
    require_all_categories: bool = False,
    require_dataset_minimums: bool = False,
) -> None:
    dataset = spec.get("dataset")
    if not isinstance(dataset, dict):
        errors.append("Missing or invalid `dataset` object.")
        return

    examples_per_category = dataset.get("examples_per_category")
    if not isinstance(examples_per_category, dict) or not examples_per_category:
        errors.append("Missing or invalid `dataset.examples_per_category` non-empty object.")
        return

    corpus_manifest = dataset.get("corpus_manifest")
    if corpus_manifest is not None:
        if not is_non_empty_string(corpus_manifest):
            errors.append("`dataset.corpus_manifest` must be a non-empty string if present.")
        else:
            manifest_path = PROJECT_ROOT / corpus_manifest if not Path(corpus_manifest).is_absolute() else Path(corpus_manifest)
            if not manifest_path.exists():
                warnings.append(f"`dataset.corpus_manifest` file not found: {corpus_manifest}")

    has_positive_supported_category = False
    present_categories: set[str] = set()

    for category, count in examples_per_category.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"`dataset.examples_per_category.{category}` must be a non-negative integer.")
            continue

        present_categories.add(category)

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

    missing_categories = GENERATOR_SUPPORTED_DATASET_CATEGORIES - present_categories
    if missing_categories:
        warnings.append(
            f"Missing dataset categories: {', '.join(sorted(missing_categories))}. "
            f"All 5 categories are expected: {', '.join(sorted(GENERATOR_SUPPORTED_DATASET_CATEGORIES))}."
        )

    if require_all_categories:
        for category in GENERATOR_SUPPORTED_DATASET_CATEGORIES:
            count = examples_per_category.get(category, 0)
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                errors.append(
                    f"`dataset.examples_per_category.{category}` must be present with a positive count "
                    f"(got {count})."
                )

    for category, minimum in MIN_DATASET_EXAMPLES_PER_CATEGORY.items():
        count = examples_per_category.get(category, 0)
        if not isinstance(count, int) or isinstance(count, bool):
            continue
        if count < minimum:
            msg = (
                f"`dataset.examples_per_category.{category}` should be at least {minimum} "
                f"for generation-ready SFT data (got {count})."
            )
            if require_dataset_minimums:
                errors.append(msg)
            else:
                warnings.append(msg)

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


def validate_spec(
    spec_path: Path,
    *,
    require_reference_docs: bool = False,
    require_reference_contract: bool = False,
    require_all_categories: bool = False,
    require_dataset_minimums: bool = False,
) -> SpecResult:
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
            if value > 3:
                warnings.append("`dialogue.max_sentences` is greater than 3; short NPC responses of 1-3 sentences are recommended.")
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
    validate_reference_docs(
        spec,
        errors,
        warnings,
        require_reference_docs=require_reference_docs,
        require_reference_contract=require_reference_contract,
    )
    validate_difficulty_levels(spec, errors, warnings)
    validate_concepts(spec, errors, warnings)
    validate_dataset(
        spec,
        errors,
        warnings,
        require_all_categories=require_all_categories,
        require_dataset_minimums=require_dataset_minimums,
    )

    return SpecResult(path=display_path, npc_key=npc_key, errors=errors, warnings=warnings)


def find_subject_specs() -> list[Path]:
    return sorted(paths.subjects_root().glob("NPC_specs/*.json"))


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
    parser.add_argument("spec", nargs="?", help="Path to one subjects/NPC_specs/*.json spec")
    parser.add_argument("--all", action="store_true", help="Validate every subjects/NPC_specs/*.json spec")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero on warnings as well as errors")
    parser.add_argument("--require-reference-docs", action="store_true", help="Fail if reference_doc file does not exist on disk")
    parser.add_argument("--require-reference-contract", action="store_true", help="Fail unless reference_doc meets minimum generation-readiness contract")
    parser.add_argument("--require-all-categories", action="store_true", help="Fail unless all 5 dataset categories have positive counts")
    parser.add_argument("--require-dataset-minimums", action="store_true", help="Fail unless all dataset categories meet minimum SFT counts")
    parser.add_argument("--generation-ready", action="store_true", help="Shortcut for reference docs, reference contract, all categories, and dataset minimums")
    args = parser.parse_args()

    if args.all and args.spec:
        parser.error("Provide a spec path or --all, not both.")
    if not args.all and not args.spec:
        parser.error("Provide a spec path or --all.")
    return args


def main() -> None:
    args = parse_args()
    spec_paths = find_subject_specs() if args.all else [Path(args.spec)]
    results = [
        validate_spec(
            path,
            require_reference_docs=args.require_reference_docs or args.generation_ready,
            require_reference_contract=args.require_reference_contract or args.generation_ready,
            require_all_categories=args.require_all_categories or args.generation_ready,
            require_dataset_minimums=args.require_dataset_minimums or args.generation_ready,
        )
        for path in spec_paths
    ]

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
