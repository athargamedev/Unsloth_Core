#!/usr/bin/env python3
"""
quick_eval.py — Evaluate a trained Unsloth LoRA model against validation questions.
Loads the model directly via unsloth (no llama-server needed), runs validation
questions from the subject spec, and produces an evaluation report + feedback JSON.
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path


def load_model(model_id, adapter_path):
    """Load model and LoRA adapter via unsloth."""
    from unsloth import FastLanguageModel
    import torch

    print(f"  Loading base model: {model_id}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_id,
        max_seq_length=2048,
        dtype=torch.bfloat16,
        load_in_4bit=True,
    )
    print(f"  Loading LoRA adapter: {adapter_path}")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=32,
        use_gradient_checkpointing="unsloth",
    )
    # Load the adapter weights
    from peft import PeftModel
    model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()
    return model, tokenizer


def run_inference(model, tokenizer, prompt, system_prompt):
    """Generate a response from the model."""
    import torch

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    inputs = tokenizer([text], return_tensors="pt").to("cuda")
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.7,
            top_p=0.9,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
        )
    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response.strip()


def main():
    parser = argparse.ArgumentParser(description="Quick eval for Unsloth LoRA models")
    parser.add_argument("--adapter", required=True, help="Path to LoRA adapter directory")
    parser.add_argument("--spec", required=True, help="Subject spec JSON path")
    parser.add_argument("--output", default=None, help="Output report path")
    parser.add_argument("--feedback-json", default=None, help="Feedback JSON output path")
    parser.add_argument("--workflow-hooks", default=None,
                        help="Path to a JSONL hook log for step tracing (default: <adapter-dir>/workflow_hooks.jsonl)")
    args = parser.parse_args()

    hook_recorder = WorkflowHookRecorder(
        args.workflow_hooks or default_hook_path(Path(args.adapter).parent),
        tool="quick_eval",
        spec_path=args.spec,
    )
    with hook_recorder.step("quick_eval", adapter=args.adapter, spec=args.spec):

        # Load spec
        with open(args.spec) as f:
            spec = json.load(f)

        npc_key = spec.get("npc_key", "unknown")
        system_prompt = spec.get("system_prompt", "")
        questions = spec.get("validation_questions", [])
        model_id = (
            spec.get("model")
            or spec.get("model_id")
            or spec.get("llm", {}).get("model_name")
            or "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
        )

        if not questions:
            hook_recorder.emit("quick_eval", "error", reason="no_validation_questions")
            print("No validation questions found in spec.")
            return

        print(f"  NPC: {npc_key}")
        print(f"  Model: {model_id}")
        print(f"  Adapter: {args.adapter}")
        print(f"  Questions: {len(questions)}")
        print()

        # Load model and adapter
        with hook_recorder.step("quick_eval_load_model", model_id=model_id, adapter=args.adapter):
            model, tokenizer = load_model(model_id, args.adapter)

        # Run inference on each question
        results = []
        print(f"\n  Running {len(questions)} validation questions...")
        with hook_recorder.step("quick_eval_run", total=len(questions)):
            for i, q in enumerate(questions):
                prompt = q.get("question", "")
                expected = q.get("expected", "")
                category = q.get("category", "general")
                concept = q.get("concept", "general")

                print(f"  [{i+1}/{len(questions)}] {category}/{concept}: {prompt[:60]}...")
                response = run_inference(model, tokenizer, prompt, system_prompt)
                results.append({
                    "question": prompt,
                    "expected": expected,
                    "response": response,
                    "category": category,
                    "concept": concept,
                })
                # Print first 200 chars of response
                print(f"    → {response[:200]}")

        # Generate report
        report = {
            "npc_key": npc_key,
            "total_questions": len(questions),
            "results": results,
        }

        output_path = args.output or f"eval/results/{npc_key}_eval_report.json"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n  Report saved: {output_path}")

        # Generate feedback JSON (group by category/concept)
        if args.feedback_json:
            per_concept = {}
            for r in results:
                key = f"{r['category']}/{r['concept']}"
                if key not in per_concept:
                    per_concept[key] = {
                        "candidate_wins": 0,
                        "total": 0,
                        "avg_candidate_quality": 0,
                        "constraint_violations": 0,
                    }
                per_concept[key]["total"] += 1
                # Simple quality heuristic: longer responses are better (avoid empty/terse)
                quality = max(0, min(50, len(r["response"]) / 5))
                per_concept[key]["avg_candidate_quality"] = (
                    (per_concept[key]["avg_candidate_quality"] * (per_concept[key]["total"] - 1) + quality)
                    / per_concept[key]["total"]
                )
                # Check for constraint violations (model refusing or giving non-answer)
                if "cannot" in r["response"].lower() and "teach" in r["response"].lower():
                    per_concept[key]["constraint_violations"] += 1
                if len(r["response"]) < 20:
                    per_concept[key]["constraint_violations"] += 1

            feedback = {
                "npc_key": npc_key,
                "candidate": str(args.adapter),
                "baseline": "(first run - no baseline)",
                "total_examples": len(questions),
                "candidate_wins": 0,  # No comparison without baseline
                "win_rate": 0.0,
                "per_concept": per_concept,
            }

            fb_path = Path(args.feedback_json)
            fb_path.parent.mkdir(parents=True, exist_ok=True)
            with open(fb_path, "w") as f:
                json.dump(feedback, f, indent=2)
            print(f"  Feedback JSON saved: {fb_path}")

        # Print summary
        print(f"\n{'=' * 50}")
        print(f"  EVALUATION SUMMARY")
        print(f"{'=' * 50}")
        for r in results:
            cat_concept = f"{r['category']}/{r['concept']}"
            print(f"  {cat_concept:40s} {len(r['response']):4d} chars")
        print(f"\n  Total: {len(results)} questions evaluated")
        print(f"  Report: {output_path}")


if __name__ == "__main__":
    main()
