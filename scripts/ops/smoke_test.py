#!/usr/bin/env python3
"""
smoke_test.py — Rapid Post-Export GGUF Validator

This script performs quick inference tests on an exported GGUF model to
ensure it maintains its persona and hasn't suffered from mode collapse.

Usage:
    ./ucore smoke exports/my_npc/my_model.gguf --spec subjects/NPC_specs/my_npc.json
    python scripts/ops/smoke_test.py exports/my_npc/my_model.gguf --track

Technical Details:
- Input: GGUF model file and optional subject spec.
- Output: Pass/Fail report and (optional) Supabase test tracking.
- Requirements: Requires llama-cli or llama.cpp binary in PATH.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
from scripts._repo_root import PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

def run_llama_cli(model_path, prompt, system_prompt=None, max_tokens=128):
    """Run inference using llama.cpp CLI or server."""
    llama_bin = None
    use_server = False
    candidates = ["llama-cli", "llama.cpp/main", "./main", "main"]
    for c in candidates:
        if subprocess.run(["which", c], capture_output=True).returncode == 0:
            llama_bin = c
            break

    if not llama_bin:
        # Check standard unsloth/llama.cpp locations — first llama-cli, then server
        unsloth_dir = Path.home() / ".unsloth/llama.cpp/build/bin"
        llama_cli = unsloth_dir / "llama-cli"
        llama_server = unsloth_dir / "llama-server"
        if llama_cli.exists():
            llama_bin = str(llama_cli)
        elif llama_server.exists():
            llama_bin = str(llama_server)
            use_server = True

    if not llama_bin:
        return "[ERROR] llama-cli or llama-server not found in PATH or ~/.unsloth"

    if use_server:
        return _run_via_server(llama_bin, model_path, prompt, system_prompt, max_tokens)

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


def _run_via_server(server_bin, model_path, prompt, system_prompt=None, max_tokens=128):
    """Run inference by briefly starting llama-server and calling its HTTP API."""
    import requests
    import socket
    import time

    # Find a free port
    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    messages = [{"role": "user", "content": prompt}]
    if system_prompt:
        messages.insert(0, {"role": "system", "content": system_prompt})

    proc = subprocess.Popen(
        [server_bin, "-m", str(model_path), "--port", str(port),
         "-ngl", "99", "--no-web"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    try:
        # Wait for server to be ready
        url = f"http://127.0.0.1:{port}/v1/chat/completions"
        for _ in range(30):
            time.sleep(0.5)
            try:
                r = requests.get(f"http://127.0.0.1:{port}/health", timeout=2)
                if r.status_code == 200:
                    break
            except requests.ConnectionError:
                continue
        else:
            proc.kill()
            return "[ERROR] llama-server failed to start within 15s"

        req = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "repeat_penalty": 1.1,
        }
        r = requests.post(url, json=req, timeout=60)
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[ERROR] Server inference failed: {e}"
    finally:
        proc.kill()
        proc.wait(timeout=5)

def check_gguf_integrity(model_path: Path) -> bool:
    """Quick integrity check: verify GGUF magic bytes and read header fields.
    
    Returns True if valid, False otherwise.
    """
    import struct
    try:
        with open(model_path, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                print(f"  ✗  Invalid GGUF magic bytes: {magic.hex()!r}")
                return False
            version = struct.unpack("<I", f.read(4))[0]
            tensor_count = struct.unpack("<Q", f.read(8))[0]
            metadata_len = struct.unpack("<Q", f.read(8))[0]
            file_size = model_path.stat().st_size
            print(f"  ✓  Valid GGUF v{version}")
            print(f"     Tensors: {tensor_count}, Metadata header: {metadata_len} bytes")
            print(f"     File size: {file_size / 1e9:.2f} GB")
        return True
    except Exception as e:
        print(f"  ✗  Integrity check failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Smoke test a GGUF model")
    parser.add_argument("model", help="Path to GGUF model")
    parser.add_argument("--spec", help="Path to subject spec JSON")
    parser.add_argument("--prompt", dest="prompts", action="append",
                        help="Custom prompt to test; may be provided multiple times")
    parser.add_argument("--track", action="store_true", help="Track results in Supabase")
    parser.add_argument("--check-integrity", action="store_true",
                        help="Validate GGUF file structure (no inference required)")
    
    args = parser.parse_args()
    
    model_path = Path(args.model)
    if not model_path.exists():
        print(f"Error: Model {model_path} not found")
        return

    if args.check_integrity:
        valid = check_gguf_integrity(model_path)
        sys.exit(0 if valid else 1)

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
