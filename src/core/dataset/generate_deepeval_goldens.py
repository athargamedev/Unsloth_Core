#!/usr/bin/env python3
"""
DeepEval Synthesizer Script for NPC LoRA Training Data.
Generates multi-turn and adversarial goldens using DeepEval.
This replaces NotebookLM for automated, non-rate-limited production datasets.
"""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

try:
    from deepeval.dataset import EvaluationDataset
    from deepeval.models import OllamaModel
    from deepeval.synthesizer import Synthesizer
except ImportError:
    print("deepeval is not installed. Please install it using `pip install deepeval`.")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def ensure_directory(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


async def generate_deepeval_dataset(spec_path: str, output_dir: str, num_cases: int = 30):
    spec_file = Path(spec_path)
    if not spec_file.exists():
        print(f"Spec file not found: {spec_file}")
        sys.exit(1)

    with spec_file.open() as f:
        spec = json.load(f)

    npc_key = spec.get("npc_key")
    if not npc_key:
        print("Spec is missing npc_key.")
        sys.exit(1)

    ref_doc = spec.get("reference_doc")
    if not ref_doc:
        print("Spec is missing reference_doc.")
        sys.exit(1)

    ref_doc_path = PROJECT_ROOT / ref_doc
    if not ref_doc_path.exists():
        print(f"Reference doc not found: {ref_doc_path}")
        sys.exit(1)

    print(f"Loading reference doc: {ref_doc_path}")
    text = ref_doc_path.read_text(encoding="utf-8")
    chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 50]

    judge_model = os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b")
    judge_base_url = os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434")
    judge = OllamaModel(
        model=judge_model,
        base_url=judge_base_url,
        temperature=float(os.getenv("DEEPEVAL_OLLAMA_TEMPERATURE", "0.7")),
    )

    synthesizer = Synthesizer(model=judge, async_mode=True)
    print(f"\nSynthesizing {num_cases} goldens for {npc_key} using DeepEval ({judge_model})...")

    # Actually generate the test cases
    try:
        synthesizer.generate_goldens_from_contexts(
            contexts=[chunks], max_goldens_per_context=num_cases
        )
    except Exception as e:
        print(f"Synthesis failed: {e}")
        sys.exit(1)

    if not synthesizer.synthetic_goldens:
        print("No test cases generated.")
        sys.exit(1)

    print(
        f"Generated {len(synthesizer.synthetic_goldens)} cases. Formatting for SFT (Unsloth_Core)..."
    )

    # Construct the base system prompt from the spec
    sys_prompt = f"""## IDENTITY
Name: {spec.get("npc_name")} | Role: {spec.get("identity", {}).get("background")}
Setting: {spec.get("game_context", {}).get("setting")}
Player Relation: {spec.get("game_context", {}).get("relationship_to_player")}

## VOICE
{spec.get("identity", {}).get("personality")} | {spec.get("identity", {}).get("mannerisms")}
Speak exactly 3-5 descriptive sentences (~500 characters) | NO markdown formatting, lists, or bullets

## KNOWLEDGE
{", ".join(spec.get("teaching", {}).get("expertise", []))}

## RULES
NEVER present speculation as fact | NEVER promote misinformation or conspiracy theories
Prefer primary sources, clear context, and cause/effect explanations"""

    # Format into SFT rows
    sft_rows = []
    for case in synthesizer.synthetic_goldens:
        row = {
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": case.input},
                {"role": "assistant", "content": case.expected_output},
            ],
            "metadata": {
                "npc_key": npc_key,
                "category": "dialogue",  # Default category for synthetics
                "technique": "deepeval",
                "source": "deepeval_synthesizer",
                "concept": case.context[0][:50] if case.context else "general",
                "difficulty": "intermediate",
                "content_hash": uuid.uuid4().hex,
            },
        }
        sft_rows.append(row)

    out_dir_path = Path(output_dir) / npc_key / "deepeval"
    ensure_directory(out_dir_path / "train_clean.jsonl")

    output_file = out_dir_path / "train_clean.jsonl"
    with output_file.open("w") as f:
        for row in sft_rows:
            f.write(json.dumps(row) + "\n")

    print(f"\nSuccess! Wrote {len(sft_rows)} SFT rows to {output_file}")
    print("These are ready for `ucore dataset-eval` and `ucore train`.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate NPC dataset using DeepEval Synthesizer")
    parser.add_argument("spec", help="Path to NPC spec JSON")
    parser.add_argument(
        "--out", default=str(PROJECT_ROOT / "subjects" / "datasets"), help="Output directory base"
    )
    parser.add_argument("--num", type=int, default=30, help="Number of test cases to generate")
    args = parser.parse_args()

    asyncio.run(generate_deepeval_dataset(args.spec, args.out, args.num))
