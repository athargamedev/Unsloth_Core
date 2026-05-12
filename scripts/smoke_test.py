#!/usr/bin/env python3
"""
smoke_test.py — Rapidly validate a GGUF model after export.

Usage:
    python scripts/smoke_test.py exports/my_npc/my_model.gguf --spec subjects/my_npc.json
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def run_llama_cli(model_path, prompt, system_prompt=None, max_tokens=128):
    """Run a single inference using llama-cli (if available) or llama.cpp main."""
    # Try to find llama-cli or main
    llama_bin = None
    candidates = ["llama-cli", "llama.cpp/main", "./main", "main"]
    for c in candidates:
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            llama_bin = c
            break
    
    if not llama_bin:
        # Check standard unsloth/llama.cpp locations
        unsloth_llama = Path.home() / ".unsloth/llama.cpp/build/bin/llama-cli"
        if unsloth_llama.exists():
            llama_bin = str(unsloth_llama)
    
    if not llama_bin:
        return "[ERROR] llama-cli or main binary not found in PATH or ~/.unsloth"

    full_prompt = prompt
    if system_prompt:
        # ChatML format
        full_prompt = f"<|im_start|>system\n{system_prompt}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"

    cmd = [
        llama_bin,
        "-m", str(model_path),
        "-p", full_prompt,
        "-n", str(max_tokens),
        "--temp", "0.7",
        "--repeat-penalty", "1.1",
        "-ngl", "99", # GPU offload
        "--log-disable"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = res.stdout
        # Extract assistant response (after the last <|im_start|>assistant\n)
        if "<|im_start|>assistant\n" in output:
            output = output.split("<|im_start|>assistant\n")[-1]
        elif "assistant\n" in output:
             output = output.split("assistant\n")[-1]
        
        # Clean up tags
        output = output.split("<|im_end|>")[0].strip()
        return output
    except Exception as e:
        return f"[ERROR] Inference failed: {e}"

def main():
    parser = argparse.ArgumentParser(description="Smoke test a GGUF model")
    parser.add_argument("model", help="Path to GGUF model")
    parser.add_argument("--spec", help="Path to subject spec JSON")
    parser.add_argument("--prompt", dest="prompts", action="append",
                        help="Custom prompt to test; may be provided multiple times")
    parser.add_argument("--track", action="store_true", help="Track results in Supabase")
    
    args = parser.parse_args()
    
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: Model {model_path} not found")
        return

    npc_key = "unknown"
    system_prompt = None
    test_prompts = ["Who are you?", "Tell me something interesting about your subject."]
    
    if args.spec:
        with open(args.spec) as f:
            spec = json.load(f)
            npc_key = spec.get("npc_key", "unknown")
            system_prompt = spec.get("system_prompt")
            npc_name = spec.get("npc_name", "the NPC")
            # Use some templates from the spec categories if available
            test_prompts = [
                f"Who are you?",
                f"What is your name?",
                f"Can you explain the basics of {spec.get('subject', 'your subject')}?"
            ]

    if args.prompts:
        test_prompts = args.prompts

    print(f"Smoke testing: {model_path.name}")
    if system_prompt:
        print(f"System prompt loaded from spec")
    print("-" * 40)

    results = []
    success_count = 0
    for prompt in test_prompts:
        print(f"User: {prompt}")
        response = run_llama_cli(model_path, prompt, system_prompt)
        print(f"NPC:  {response}")
        
        # Basic sanity checks
        is_sane = True
        reason = None
        if "[ERROR]" in response:
            is_sane = False
            reason = "Error"
        elif len(response) < 5:
            is_sane = False
            reason = "Too short"
        elif "I am an AI" in response or "language model" in response:
            print("  [WARN] AI disclaimer detected!")
            is_sane = False
            reason = "AI disclaimer"
            
        if is_sane:
            success_count += 1
        
        results.append({
            "prompt": prompt,
            "response": response,
            "is_sane": is_sane,
            "reason": reason
        })
        print("-" * 40)

    print(f"Smoke test complete: {success_count}/{len(test_prompts)} prompts passed basic sanity check.")

    if args.track:
        from scripts.track_eval_results import track_result, track_per_example_result
        print(f"[track] Storing smoke test results in Supabase...")
        
        track_result(
            npc_key=npc_key,
            model_path=str(model_path),
            win_rate=success_count / len(test_prompts) if test_prompts else 0,
            notes=f"Smoke test: {success_count}/{len(test_prompts)} passed",
            metadata={"test_type": "smoke_test"}
        )
        
        test_run_name = f"Smoke_{npc_key}_{datetime.now().strftime('%Y%m%d_%H%M')}"
        for res in results:
            track_per_example_result(
                npc_key=npc_key,
                test_name=test_run_name,
                prompt=res["prompt"],
                response=res["response"],
                score=1.0 if res["is_sane"] else 0.0,
                metadata={"reason": res["reason"]}
            )

if __name__ == "__main__":
    main()
