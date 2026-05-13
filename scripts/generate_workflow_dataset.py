#!/usr/bin/env python3
"""
generate_workflow_dataset.py — Fast programmatic dataset generator.

Reads all project markdown docs, extracts sections, and generates Q&A pairs
by using section headings as question templates and content as answers.
No LLM calls needed — runs in seconds.

Usage:
    python scripts/generate_workflow_dataset.py
    python scripts/generate_workflow_dataset.py --output datasets/workflow_assistant/ollama/train.jsonl
"""

import argparse
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Docs to include (relative to PROJECT_ROOT) — ordered by importance
DOC_PATHS = [
    "AGENTS.md",
    "docs/reference/CLI_REFERENCE.md",
    "docs/reference/SUBJECT_SPEC.md",
    "docs/TRAINING_WORKFLOW.md",
    "docs/DATASET_CONTRACT_WORKFLOW.md",
    "docs/EXPORT_WORKFLOW.md",
    "docs/EVALUATION_WORKFLOW.md",
    "docs/CONFIG_VALIDATION_WORKFLOW.md",
    "docs/NOTEBOOKLM_WORKFLOW.md",
    "docs/OLLAMA_WORKFLOW.md",
    "docs/architecture/PIPELINE_FLOW.md",
    "docs/architecture/SUPABASE_SCHEMA.md",
    "docs/integration/FRONTEND_DASHBOARD.md",
    "docs/LLAMA_UNITY_PROFILE.md",
    "docs/NPC_LORA_WORKFLOW_CONTRACT.md",
    "docs/SUPABASE_INTEGRATION_CHECKLIST.md",
    "frontend_control/DOCUMENTATION.md",
]

WORKFLOW_SYSTEM_PROMPT = """You are the Unsloth_Core Workflow Assistant — a specialist in the NPC fine-tuning pipeline for Unity games. You know the 4-stage pipeline (Generation → Sanitization → Training → Export), all CLI flags and presets, and the frontend dashboard operations. Keep answers concise and actionable. Suggest exact ./ucore commands when applicable."""


# ── Question templates mapped to section heading patterns ────────────────────

QUESTION_TEMPLATES = {
    "overview": [
        "What is covered in {heading}?",
        "Give me an overview of {heading}.",
        "What do I need to know about {heading}?",
    ],
    "cli": [
        "What does the `{heading}` command do?",
        "How do I use `{heading}`?",
        "What are the flags for `{heading}`?",
    ],
    "pipeline": [
        "How does the {heading} stage work?",
        "What happens during {heading}?",
        "What are the inputs and outputs of {heading}?",
    ],
    "config": [
        "How do I configure {heading}?",
        "What settings are available for {heading}?",
        "Explain the {heading} configuration.",
    ],
    "workflow": [
        "Walk me through the {heading} workflow.",
        "How do I run {heading}?",
        "What are the steps for {heading}?",
    ],
    "troubleshooting": [
        "How do I fix {heading}?",
        "What causes {heading} and how do I resolve it?",
        "Troubleshoot {heading}.",
    ],
    "reference": [
        "What is the format for {heading}?",
        "Explain the {heading} structure.",
        "What fields are in {heading}?",
    ],
    "integration": [
        "How does {heading} work?",
        "Explain the {heading} architecture.",
        "What are the key components of {heading}?",
    ],
    "default": [
        "Tell me about {heading}.",
        "What should I know about {heading}?",
        "Explain {heading} in detail.",
    ],
}


def classify_heading(heading: str) -> str:
    """Classify a heading into a template category."""
    hl = heading.lower()
    if any(w in hl for w in ["overview", "introduction", "summary"]):
        return "overview"
    if any(w in hl for w in ["cli", "command", "flag", "./ucore", "`"]):
        return "cli"
    if any(w in hl for w in ["pipeline", "stage", "generation", "sanitization", "training", "export", "evaluat"]):
        return "pipeline"
    if any(w in hl for w in ["config", "setting", "parameter", "hyperparameter"]):
        return "config"
    if any(w in hl for w in ["workflow", "how to", "step", "guide", "usage"]):
        return "workflow"
    if any(w in hl for w in ["troubleshoot", "fix", "error", "issue", "problem", "fail"]):
        return "troubleshooting"
    if any(w in hl for w in ["format", "schema", "structure", "field", "type", "object", "interface"]):
        return "reference"
    if any(w in hl for w in ["architecture", "integration", "component", "endpoint"]):
        return "integration"
    return "default"


def extract_key_sentences(text: str, max_sentences: int = 6) -> str:
    """Extract the most important sentences from a block of text."""
    # Remove markdown formatting
    cleaned = re.sub(r"[#*`_~]", "", text)
    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    # Filter out code blocks, urls, empty lines
    good = [s.strip() for s in sentences if len(s.strip()) > 20 and not s.strip().startswith("```")]
    # Take first few meaningful sentences
    return " ".join(good[:max_sentences])


def chunk_markdown(text: str) -> list[tuple[str, str]]:
    """Split a markdown file into (heading, content) sections."""
    lines = text.split("\n")
    sections = []
    current_heading = "Overview"
    current_content: list[str] = []

    for line in lines:
        heading_match = re.match(r"^#{2,4}\s+(.+)$", line)
        if heading_match:
            if current_content:
                body = "\n".join(current_content).strip()
                if len(body) > 50:
                    sections.append((current_heading, body))
            current_heading = heading_match.group(1).strip()
            current_content = []
        else:
            current_content.append(line)

    if current_content:
        body = "\n".join(current_content).strip()
        if len(body) > 50:
            sections.append((current_heading, body))

    return sections


# ── Answer generators ───────────────────────────────────────────────────────

def generate_answers(heading: str, content: str) -> list[tuple[str, str]]:
    """Generate (question, answer) pairs from a section's heading and content."""
    category = classify_heading(heading)
    templates = QUESTION_TEMPLATES[category]

    # Extract key info from content
    summary = extract_key_sentences(content, max_sentences=8)

    # Find code blocks for commands
    code_blocks = re.findall(r"```(?:\w+)?\n(.*?)```", content, re.DOTALL)
    commands = []
    for cb in code_blocks:
        for line in cb.split("\n"):
            line = line.strip()
            if line.startswith("./ucore") or line.startswith("python ") or line.startswith("npm "):
                commands.append(line)

    # Build answers
    pairs = []
    for i, template in enumerate(templates[:3]):  # max 3 per section
        question = template.replace("{heading}", heading)

        # Craft answer from content
        answer_parts = [summary]

        if commands:
            cmd = commands[i % len(commands)]
            answer_parts.append(f"\n\nExample command:\n```\n{cmd}\n```")

        answer = " ".join(answer_parts)
        pairs.append((question, answer))

    return pairs


def read_all_docs(root: Path) -> list[tuple[str, str, str]]:
    """Read all docs and return list of (filename, heading, content)."""
    chunks: list[tuple[str, str, str]] = []
    for rel_path in DOC_PATHS:
        abs_path = root / rel_path
        if not abs_path.exists():
            print(f"  [SKIP] {rel_path} not found")
            continue
        try:
            text = abs_path.read_text(encoding="utf-8")
            sections = chunk_markdown(text)
            for heading, content in sections:
                chunks.append((rel_path, heading, content))
            print(f"  [OK]   {rel_path} → {len(sections)} sections")
        except Exception as e:
            print(f"  [ERR]  {rel_path}: {e}")
    return chunks


def to_chatml(qa_pairs: list[tuple[str, str]]) -> list[dict]:
    """Convert Q&A pairs to ChatML format rows."""
    rows = []
    for question, answer in qa_pairs:
        rows.append({
            "messages": [
                {"role": "system", "content": WORKFLOW_SYSTEM_PROMPT},
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer},
            ]
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Generate Workflow Assistant training dataset")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "datasets" / "workflow_assistant" / "ollama" / "train.jsonl"))
    parser.add_argument("--dry-run", action="store_true", help="Only list counts, don't write")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f" Workflow Assistant Dataset Generator (programmatic)")
    print(f" Output: {args.output}")
    print(f"{'='*60}\n")

    print("Reading documentation...")
    chunks = read_all_docs(PROJECT_ROOT)
    print(f"\nTotal: {len(chunks)} sections across {len(DOC_PATHS)} files\n")

    # Generate Q&A pairs
    all_rows: list[dict] = []
    for file, heading, content in chunks:
        qa_pairs = generate_answers(heading, content)
        rows = to_chatml(qa_pairs)
        all_rows.extend(rows)

    if args.dry_run:
        print(f"Would generate {len(all_rows)} training rows from {len(chunks)} sections")
        print(f"\nSample rows:")
        for row in all_rows[:3]:
            q = row["messages"][1]["content"]
            a = row["messages"][2]["content"][:80]
            print(f"  Q: {q}")
            print(f"  A: {a}...\n")
        return

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for row in all_rows:
            f.write(json.dumps(row) + "\n")

    print(f"\n{'='*60}")
    print(f" Done! {len(all_rows)} training rows written to:")
    print(f"   {output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
