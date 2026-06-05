import asyncio
import json
import os
import sys
from pathlib import Path

# Try importing DeepEval components; we can use its prompt templating or models
try:
    from deepeval.models import OllamaModel
except ImportError:
    print("deepeval not installed. Please install it.")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def repair_failures(npc_key: str, technique: str):
    base_dir = PROJECT_ROOT / "data" / "datasets" / npc_key / technique
    failures_path = base_dir / "quality_failures.json"
    train_path = base_dir / "train_clean.jsonl"
    repaired_path = base_dir / "train_repaired.jsonl"

    if not failures_path.exists():
        print(f"No quality_failures.json found at {failures_path}")
        return

    with failures_path.open() as f:
        failures = json.load(f)

    if not failures:
        print("No failures to repair.")
        return

    # Load primer
    primer_path = PROJECT_ROOT / "subjects" / "reference_docs" / f"{npc_key}_primer.md"
    primer_text = primer_path.read_text(encoding="utf-8") if primer_path.exists() else ""

    # Setup Model
    judge_model = os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b")
    judge_base_url = os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434")
    model = OllamaModel(model=judge_model, base_url=judge_base_url, temperature=0.7)

    # Read training data into memory
    with train_path.open() as f:
        train_lines = f.readlines()

    repaired_count = 0
    for failure in failures:
        test_name = failure.get("test_name")
        input_data = failure.get("input")
        actual_output = failure.get("actual_output")
        metric = failure.get("metric", {})
        reason = metric.get("reason", "No reason provided.")
        metadata = failure.get("metadata", {})
        line_number = metadata.get("line_number")

        if not line_number:
            continue

        print(f"\nRepairing Line {line_number}: {test_name}")
        print(f"Reason: {reason}")

        prompt = f"""
You are an expert editor for NPC dialogue. An AI generated a response that failed quality evaluation.
Your task is to REWRITE the response to fix the failure, adhering strictly to the NPC's reference primer.

Reference Primer:
{primer_text}

Original Evaluation Context (Input):
{input_data}

Failed Output:
{actual_output}

Failure Reason (Feedback):
{reason}

Rewrite the output to completely address the failure reason. Provide ONLY the new, corrected dialogue. Do not include markdown, quotes, or conversational filler like 'Here is the rewrite'.
        """.strip()

        try:
            # We can use model.generate
            result, _ = await model.a_generate(prompt)
            new_output = result.strip()

            # Update the specific line
            idx = line_number - 1
            if 0 <= idx < len(train_lines):
                row = json.loads(train_lines[idx])

                # Find assistant message and replace
                for msg in row.get("messages", []):
                    if msg.get("role") == "assistant":
                        msg["content"] = new_output

                # Tag it as repaired
                row.setdefault("metadata", {})["repaired"] = True
                row["metadata"]["repair_reason"] = reason

                train_lines[idx] = json.dumps(row) + "\n"
                repaired_count += 1
                print(f"-> Repaired: {new_output[:100]}...")

        except Exception as e:
            print(f"Failed to repair line {line_number}: {e}")

    # Write repaired file
    with repaired_path.open("w") as f:
        f.writelines(train_lines)

    print(f"\nSuccessfully repaired {repaired_count} failures. Saved to {repaired_path.name}")
    print("Run validation on the new file and then overwrite train_clean.jsonl if satisfied.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python feedback_loop_deepeval.py <npc_key> <technique>")
        sys.exit(1)
    asyncio.run(repair_failures(sys.argv[1], sys.argv[2]))
