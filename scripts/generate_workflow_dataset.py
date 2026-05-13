#!/usr/bin/env python3
"""
generate_workflow_dataset.py — Generate training data for the Workflow Assistant.

Reads all project documentation markdown files, chunks them into sections,
and uses a local Ollama model to generate high-quality Q&A pairs in ChatML format.

Usage:
    python scripts/generate_workflow_dataset.py
    python scripts/generate_workflow_dataset.py --model llama3.1 --output datasets/workflow_assistant/ollama/train.jsonl
    python scripts/generate_workflow_dataset.py --dry-run  # preview without generating
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests  # noqa: E402 (needed in generate_qa_batch below)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

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

# ── QA Generation Prompt ─────────────────────────────────────────────────────

QA_SYSTEM_PROMPT = """You are generating training data for a Workflow Assistant AI that helps users with the Unsloth_Core project (an NPC fine-tuning pipeline for Unity games).

For each document section provided, generate 3-5 question-answer pairs that:
1. Cover the most important concepts in that section
2. Include practical "how to" questions where applicable
3. Reference exact file paths, CLI flags, and commands when relevant
4. Answers should be 2-6 sentences, concise and actionable

Output format: a JSON array of objects with "question" and "answer" fields.
Only output the JSON array, nothing else."""

# ── Section Chunking ─────────────────────────────────────────────────────────

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


# ── QA Generation via Ollama ──────────────────────────────────────────────────

def generate_qa_batch(
    chunk: tuple[str, str, str],
    model: str,
    max_retries: int = 3,
) -> list[dict]:
    """Send a doc section to Ollama and get back Q&A pairs."""
    filename, heading, content = chunk

    # Build the prompt with context
    prompt = f"""Document: {filename}
Section: {heading}

Content:
{content[:3000]}

---

Generate 3-5 question-answer pairs that teach a Workflow Assistant about Unsloth_Core based on the section above."""

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model": model,
                    "system": QA_SYSTEM_PROMPT,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.4, "num_predict": 4096},
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("response", "").strip()

            # Try to extract JSON array from the response
            # The model might wrap it in markdown code blocks
            json_match = re.search(r"\[[\s\S]*\]", raw)
            if json_match:
                candidates = json.loads(json_match.group())
            else:
                candidates = json.loads(raw)

            if not isinstance(candidates, list):
                print(f"    ⚠ Non-array response for {filename} › {heading[:40]}")
                return []

            # Validate shape
            for c in candidates:
                if not isinstance(c, dict) or "question" not in c or "answer" not in c:
                    print(f"    ⚠ Malformed Q&A in {filename} › {heading[:40]}")
                    return []

            print(f"    ✓ {len(candidates)} Q&A pairs")
            return candidates

        except (json.JSONDecodeError, KeyError, requests.RequestException) as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"    ⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"    ✗ Failed after {max_retries} attempts: {e}")
                return []


# ── ChatML Output ────────────────────────────────────────────────────────────

def to_chatml(system_prompt: str, qa_pairs: list[dict]) -> list[dict]:
    """Convert Q&A pairs to ChatML format rows."""
    rows = []
    for qa in qa_pairs:
        rows.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": qa["question"]},
                {"role": "assistant", "content": qa["answer"]},
            ]
        })
    return rows


WORKFLOW_SYSTEM_PROMPT = """You are the Unsloth_Core Workflow Assistant — a specialist in the NPC fine-tuning pipeline for Unity games. You know the 4-stage pipeline (Generation → Sanitization → Training → Export), all CLI flags and presets, and the frontend dashboard operations. Keep answers concise and actionable. Suggest exact ./ucore commands when applicable."""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate Workflow Assistant training dataset")
    parser.add_argument("--model", default="gemma4:e2b", help="Ollama model to use for generation")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "datasets" / "workflow_assistant" / "ollama" / "train.jsonl"))
    parser.add_argument("--dry-run", action="store_true", help="Only list sections, don't generate")
    parser.add_argument("--max-chunks", type=int, default=0, help="Max chunks to process (0 = all)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between Ollama calls (seconds)")
    args = parser.parse_args()

    # Process chunks
    print(f" Workflow Assistant Dataset Generator")
    print(f" Model: {args.model}")
    print(f" Output: {args.output}")
    print(f"{'='*60}\n")

    # Read docs
    print("Reading documentation...")
    chunks = read_all_docs(PROJECT_ROOT)
    print(f"\nTotal: {len(chunks)} sections across {len(DOC_PATHS)} files\n")

    if args.dry_run:
        print("DRY RUN — sections found:")
        for i, (file, heading, content) in enumerate(chunks):
            preview = content[:80].replace("\n", " ")
            print(f"  {i+1:3d}. [{file}] {heading}")
            print(f"       {preview}...")
        return

    # Process chunks
    if args.max_chunks > 0:
        chunks = chunks[:args.max_chunks]

    all_pairs: list[dict] = []
    total_rows = 0

    print("Generating Q&A pairs...")
    for i, chunk in enumerate(chunks):
        file, heading, content = chunk
        print(f"\n[{i+1}/{len(chunks)}] {file} › {heading[:60]}")
        
        qa_pairs = generate_qa_batch(chunk, args.model)
        rows = to_chatml(WORKFLOW_SYSTEM_PROMPT, qa_pairs)

        all_pairs.extend(rows)
        total_rows += len(rows)

        if args.delay > 0:
            time.sleep(args.delay)

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for row in all_pairs:
            f.write(json.dumps(row) + "\n")

    print(f"\n{'='*60}")
    print(f" Done! {total_rows} training rows written to:")
    print(f"   {output_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
