#!/usr/bin/env python3
"""
generate_workflow_dataset.py — Manifest-driven Workflow Assistant dataset generator.

Builds ChatML training + validation data from a curated corpus manifest of
checked-in docs and structured reports. Questions are practical and curated in
the manifest; answers are assembled from matched sections, commands, bullets,
and tables inside each source document.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

from scripts._repo_root import PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))
from _config import paths
from _config import constants as C
DEFAULT_MANIFEST = PROJECT_ROOT / "docs" / "corpora" / "workflow_assistant_docs.json"

WORKFLOW_SYSTEM_PROMPT = (
    "You are WorkflowAssistant for the Unsloth_Core repository. Help with checked-in docs, "
    "structured reports, CLI usage, dataset generation, sanitization, training, export, "
    "evaluation, and frontend dashboard operations. Speak in 1-5 short sentences, stay "
    "precise, prefer `./ucore` commands, and never pretend you executed commands or saw "
    "runtime state unless the user provided it."
)


def default_manifest_path() -> Path:
    return DEFAULT_MANIFEST


def load_json(path: str | Path) -> dict:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = PROJECT_ROOT / file_path
    return json.loads(file_path.read_text(encoding="utf-8"))


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split a markdown file into (heading, body) sections."""
    lines = text.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = "Overview"
    current_body: list[str] = []

    for line in lines:
        heading_match = re.match(r"^#{1,4}\s+(.+)$", line.strip())
        if heading_match:
            body = "\n".join(current_body).strip()
            if body:
                sections.append((current_heading, body))
            current_heading = heading_match.group(1).strip()
            current_body = []
            continue
        current_body.append(line)

    body = "\n".join(current_body).strip()
    if body:
        sections.append((current_heading, body))
    return sections


def normalize_text(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[[^\]]+\]\([^)]*\)", " ", text)
    text = re.sub(r"[>#*_~]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_sentence(text: str) -> str:
    cleaned = normalize_text(text).strip(" -:\t")
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def extract_commands(text: str) -> list[str]:
    commands: list[str] = []
    code_blocks = re.findall(r"```(?:bash|sh|shell|python)?\n(.*?)```", text, re.DOTALL)
    for block in code_blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        index = 0
        while index < len(lines):
            line = lines[index].strip()
            if not line.startswith(("./ucore", "python ", "npm ", "source ")):
                index += 1
                continue
            command_lines = [line.rstrip("\\").rstrip()]
            while line.endswith("\\") and index + 1 < len(lines):
                index += 1
                line = lines[index].strip()
                command_lines.append(line.rstrip("\\").rstrip())
            commands.append(" ".join(part for part in command_lines if part))
            index += 1
    for match in re.findall(r"`([^`]+)`", text):
        inline = match.strip()
        if inline.startswith(("./ucore", "python ", "npm ")):
            commands.append(inline)
    return dedupe(commands)


def extract_bullets(text: str) -> list[str]:
    bullets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
            bullets.append(normalize_sentence(re.sub(r"^([-*]|\d+\.)\s+", "", stripped)))
    return [bullet for bullet in dedupe(bullets) if bullet]


def extract_table_facts(text: str) -> list[str]:
    facts: list[str] = []
    generic_headers = {"field", "type", "description", "stage", "script", "input", "output", "function", "returns", "technique", "quality", "speed", "dependencies", "best for", "command", "flag", "short"}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped.replace("|", "").strip()) <= {":", "-", " "}:
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        lowered_cells = [cell.lower() for cell in cells]
        if all(cell in generic_headers for cell in lowered_cells if cell):
            continue
        if cells[0].lower() in {"field", "function", "stage", "technique", "preset", "flag"} and len(cells) >= 3:
            facts.append(normalize_sentence(f"{cells[0]} `{cells[1]}`: {cells[2]}"))
            continue
        if len(cells) >= 3 and cells[0] and cells[2]:
            facts.append(normalize_sentence(f"`{cells[0]}`: {cells[2]}"))
        elif cells[0] and cells[1]:
            facts.append(normalize_sentence(f"`{cells[0]}`: {cells[1]}"))
    return [fact for fact in dedupe(facts) if fact]


def extract_prose_sentences(text: str, limit: int = 8) -> list[str]:
    cleaned = normalize_text(text)
    if not cleaned:
        return []
    pieces = re.split(r"(?<=[.!?])\s+", cleaned)
    sentences: list[str] = []
    for piece in pieces:
        sentence = normalize_sentence(piece)
        if len(sentence) < 25:
            continue
        sentences.append(sentence)
        if len(sentences) >= limit:
            break
    return sentences


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def select_sections(sections: list[tuple[str, str]], section_hints: list[str] | None) -> list[tuple[str, str]]:
    if not section_hints:
        return sections
    lowered_hints = [hint.lower() for hint in section_hints]
    matched = [
        (heading, body)
        for heading, body in sections
        if any(hint in heading.lower() for hint in lowered_hints)
    ]
    return matched or sections


def build_answer(source_path: str, sections: list[tuple[str, str]], question_config: dict, fallback_max_sentences: int = 5) -> str:
    max_sentences = int(question_config.get("max_sentences") or fallback_max_sentences)
    summary_budget = 1 if question_config.get("include_commands") else min(2, max(1, max_sentences - 2))
    joined_text = "\n\n".join(body for _, body in sections)
    prompt = str(question_config.get("prompt", "")).lower()

    prose = extract_prose_sentences(joined_text)
    bullets = extract_bullets(joined_text)
    tables = extract_table_facts(joined_text)
    if any(token in prompt for token in ["field", "schema", "examples_per_category", "path", "directory", "layout", "record"]):
        facts = tables + bullets + prose
    elif question_config.get("include_commands"):
        facts = prose + bullets + tables
    else:
        facts = bullets + prose + tables
    facts = dedupe([fact for fact in facts if fact])
    summary_parts = facts[:summary_budget]

    if not summary_parts:
        section_names = ", ".join(heading for heading, _ in sections[:3]) or "the matched documentation"
        summary_parts = [normalize_sentence(f"The answer is documented under {section_names}")]

    answer = " ".join(summary_parts)
    commands = extract_commands(joined_text)
    if question_config.get("include_commands") and commands:
        answer += f"\n\nExample command:\n```bash\n{commands[0]}\n```"

    answer += f"\n\nReference: `{source_path}`."
    return answer.strip()


def build_manual_examples(spec: dict) -> list[dict]:
    system_prompt = spec.get("system_prompt") or WORKFLOW_SYSTEM_PROMPT
    npc_key = spec["npc_key"]
    rows = [
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Who are you in this repository?"},
                {
                    "role": "assistant",
                    "content": "I am WorkflowAssistant for Unsloth_Core. I help with checked-in docs, CLI workflows, dataset generation, sanitization, training, export, evaluation, and the frontend dashboard. I prefer exact file paths and `./ucore` commands over vague advice."
                },
            ],
            "metadata": {"npc_key": npc_key, "category": "identity", "source": "docs_manifest", "source_path": "subjects/NPC_specs/workflow_assistant.json"},
        },
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Can you execute commands or inspect my machine for me?"},
                {
                    "role": "assistant",
                    "content": "No. I can recommend the next safe `./ucore` or repo command, but I should not pretend I already ran it or saw your runtime state. If you share output, I can help interpret it."
                },
            ],
            "metadata": {"npc_key": npc_key, "category": "refusal", "source": "docs_manifest", "source_path": "subjects/NPC_specs/workflow_assistant.json"},
        },
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "What sources are safe for your training corpus?"},
                {
                    "role": "assistant",
                    "content": "Use checked-in docs and structured reports only. Avoid runtime logs, outputs, exports, registry state, secrets, and machine-local noise for this assistant path. The corpus manifest lives in `docs/corpora/workflow_assistant_docs.json`."
                },
            ],
            "metadata": {"npc_key": npc_key, "category": "refusal", "source": "docs_manifest", "source_path": "docs/corpora/workflow_assistant_docs.json"},
        },
        {
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Where should I look first if I am lost in the repo?"},
                {
                    "role": "assistant",
                    "content": "Start with `README.md` for the quick workflow, then `AGENTS.md` for the repo logic map, and `docs/MAP.md` for deeper references. After that, jump to the exact workflow doc for the stage you are working on."
                },
            ],
            "metadata": {"npc_key": npc_key, "category": "dialogue", "source": "docs_manifest", "source_path": "docs/MAP.md"},
        },
    ]
    return rows


def load_manifest_sources(manifest_path: str | Path) -> list[dict]:
    manifest = load_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Corpus manifest must contain a non-empty 'sources' array")
    return sources


def generate_workflow_dataset_from_manifest(
    spec: dict,
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    seed: int = C.DEFAULT_SEED,
    include_validation: bool = True,
    val_split: float = C.DEFAULT_VAL_SPLIT,
) -> dict:
    random.seed(seed)
    system_prompt = spec.get("system_prompt") or WORKFLOW_SYSTEM_PROMPT
    rows = build_manual_examples(spec)
    source_counts: dict[str, int] = {"manual": len(rows)}

    for source_config in load_manifest_sources(manifest_path):
        relative_path = source_config.get("path")
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError("Each manifest source must contain a non-empty 'path'")
        source_path = PROJECT_ROOT / relative_path
        if not source_path.exists():
            raise FileNotFoundError(f"Manifest source not found: {relative_path}")

        source_text = source_path.read_text(encoding="utf-8")
        sections = select_sections(chunk_markdown(source_text), source_config.get("section_hints"))
        questions = source_config.get("questions") or []
        if not isinstance(questions, list) or not questions:
            continue

        generated_here = 0
        for question_entry in questions:
            if isinstance(question_entry, str):
                question_config = {"prompt": question_entry}
            elif isinstance(question_entry, dict):
                question_config = question_entry
            else:
                raise ValueError(f"Unsupported question entry in {relative_path}: {question_entry!r}")

            prompt = question_config.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError(f"Question prompt missing in {relative_path}")

            target_sections = select_sections(sections, question_config.get("target_headings"))
            answer = build_answer(relative_path, target_sections, question_config, spec.get("dialogue", {}).get("max_sentences", 5))
            rows.append(
                {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt.strip()},
                        {"role": "assistant", "content": answer},
                    ],
                    "metadata": {
                        "npc_key": spec["npc_key"],
                        "category": question_config.get("category", "teaching"),
                        "source": "docs_manifest",
                        "source_path": relative_path,
                        "kind": source_config.get("kind", "doc"),
                    },
                }
            )
            generated_here += 1
        source_counts[relative_path] = generated_here

    random.shuffle(rows)
    if include_validation and len(rows) > C.MIN_EXAMPLES_FOR_VALIDATION:
        split = max(1, int(len(rows) * val_split))
        validation_rows = rows[:split]
        train_rows = rows[split:]
    else:
        train_rows = rows
        validation_rows = []

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in train_rows:
            handle.write(json.dumps(row) + "\n")

    validation_path = None
    if validation_rows:
        validation_path = output_path.parent / "validation.jsonl"
        with validation_path.open("w", encoding="utf-8") as handle:
            for row in validation_rows:
                handle.write(json.dumps(row) + "\n")

    return {
        "spec": spec["npc_key"],
        "total": len(rows),
        "train": len(train_rows),
        "validation": len(validation_rows),
        "categories": source_counts,
        "train_path": str(output_path),
        "val_path": str(validation_path) if validation_path else None,
        "manifest_path": str(Path(manifest_path)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate WorkflowAssistant dataset from a curated corpus manifest")
    parser.add_argument("--spec", default=str(paths.subjects_root() / "workflow_assistant.json"), help="Path to workflow assistant subject spec")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="Path to corpus manifest JSON")
    parser.add_argument("--output", default=str(paths.dataset_train_path("workflow_assistant", "docs")), help="Output train.jsonl path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-validation", action="store_true", help="Skip validation split")
    parser.add_argument("--val-split", type=float, default=0.12, help="Validation split ratio")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec = load_json(args.spec)
    result = generate_workflow_dataset_from_manifest(
        spec,
        args.manifest,
        args.output,
        seed=args.seed,
        include_validation=not args.no_validation,
        val_split=args.val_split,
    )
    print(f"Generated {result['total']} rows from {result['manifest_path']}")
    print(f"  Train: {result['train_path']} ({result['train']})")
    if result["val_path"]:
        print(f"  Validation: {result['val_path']} ({result['validation']})")


if __name__ == "__main__":
    main()
