#!/usr/bin/env python3
"""
quick_eval.py — Quick evaluation of fine-tuned models without requiring base model.

Measures:
1. Training dataset retention - does the model remember what it was trained on?
2. Instruction following - does it follow constraints?
3. Response quality metrics - diversity, coherence

Usage:
    python scripts/quick_eval.py outputs/chemistry_instructor
    python scripts/quick_eval.py outputs/chemistry_instructor --samples 50
"""

import argparse
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_validation_set(val_path, limit=None):
    """Load validation examples."""
    examples = []
    with open(val_path) as f:
        for line in f:
            if line.strip():
                examples.append(json.loads(line))
                if limit and len(examples) >= limit:
                    break
    return examples


def extract_qa(example):
    """Extract Q&A from example."""
    msgs = example.get("messages", [])
    user_msg = None
    assistant_msg = None
    for msg in msgs:
        if msg["role"] == "user":
            user_msg = msg["content"]
        elif msg["role"] == "assistant":
            assistant_msg = msg["content"]
    return user_msg, assistant_msg


def diversity_score(text):
    """Compute lexical diversity (type-token ratio)."""
    tokens = text.lower().split()
    if len(tokens) < 2:
        return 0
    unique = len(set(tokens))
    return unique / len(tokens)


def sentence_count(text):
    """Count sentences."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    return len(sentences)


def has_ai_disclaimer(text):
    """Check if response has AI disclaimers."""
    patterns = [
        r"\bI am (an|the) AI\b",
        r"\bAI (language model|assistant)\b",
        r"\bas an AI\b",
        r"I'm an AI",
    ]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def compare_similarity(expected, actual, metric="token_overlap"):
    """Compare expected vs actual response."""
    exp_tokens = set(expected.lower().split())
    act_tokens = set(actual.lower().split())
    
    if metric == "token_overlap":
        # Jaccard similarity
        if not exp_tokens and not act_tokens:
            return 1.0
        if not exp_tokens or not act_tokens:
            return 0.0
        intersection = len(exp_tokens & act_tokens)
        union = len(exp_tokens | act_tokens)
        return intersection / union if union > 0 else 0.0
    
    return 0.0


def evaluate_model_local(model_path, val_set, spec=None, max_samples=10):
    """Evaluate model locally using llama-cpp-python without starting server."""
    try:
        from llama_cpp import Llama
    except ImportError:
        print("Error: llama-cpp-python not installed")
        print("Install with: pip install llama-cpp-python")
        return None

    print(f"[eval] Loading model: {model_path}")
    
    try:
        # Load model (LoRA merged or standalone GGUF)
        llm = Llama(
            model_path=str(model_path),
            n_gpu_layers=-1,  # Use GPU
            n_ctx=2048,
            verbose=False,
        )
    except Exception as e:
        print(f"[eval] Error loading model: {e}")
        print("[eval] Make sure you've merged the LoRA with base model:")
        print("  python scripts/export.py chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
        return None

    results = []
    
    print(f"\n[eval] Running inference on {min(len(val_set), max_samples)} examples...")
    for idx, example in enumerate(val_set[:max_samples]):
        user_q, expected = extract_qa(example)
        if not user_q or not expected:
            continue

        try:
            # Build prompt
            prompt = f"User: {user_q}\nAssistant:"
            
            # Generate response
            start = time.time()
            response = llm(prompt, max_tokens=256, temperature=0.7, top_p=0.95)
            latency = time.time() - start
            
            generated = response["choices"][0]["text"].strip()
            
            # Metrics
            metrics = {
                "question": user_q[:60],
                "expected_length": len(expected.split()),
                "generated_length": len(generated.split()),
                "latency": round(latency, 2),
                "diversity": round(diversity_score(generated), 3),
                "sentences": sentence_count(generated),
                "has_ai_disclaimer": has_ai_disclaimer(generated),
                "token_overlap": round(compare_similarity(expected, generated), 3),
                "expected_preview": expected[:100],
                "generated_preview": generated[:100],
            }
            
            results.append(metrics)
            
            print(f"  [{idx+1}/{min(len(val_set), max_samples)}] "
                  f"len={metrics['generated_length']}, "
                  f"sim={metrics['token_overlap']}, "
                  f"time={metrics['latency']:.1f}s")
            
        except Exception as e:
            print(f"  [{idx+1}] Error: {e}")
            continue

    return results


def report(results, spec=None):
    """Generate evaluation report."""
    if not results:
        print("[eval] No results to report")
        return
    
    print("\n" + "=" * 70)
    print("  EVALUATION REPORT")
    print("=" * 70)
    
    # Aggregate metrics
    avg_len = sum(r["generated_length"] for r in results) / len(results)
    avg_diversity = sum(r["diversity"] for r in results) / len(results)
    avg_similarity = sum(r["token_overlap"] for r in results) / len(results)
    avg_latency = sum(r["latency"] for r in results) / len(results)
    has_disclaimer = sum(1 for r in results if r["has_ai_disclaimer"])
    
    print(f"\n📊 METRICS ({len(results)} examples):")
    print(f"  Average response length:    {avg_len:.0f} tokens")
    print(f"  Average diversity (TTR):    {avg_diversity:.2%}")
    print(f"  Average token overlap:      {avg_similarity:.2%} (semantic similarity)")
    print(f"  Average latency:            {avg_latency:.2f}s per response")
    print(f"  Responses with AI claim:    {has_disclaimer}/{len(results)}")
    
    # Show quality buckets
    print(f"\n🎯 QUALITY DISTRIBUTION:")
    excellent = sum(1 for r in results if r["token_overlap"] >= 0.6)
    good = sum(1 for r in results if 0.4 <= r["token_overlap"] < 0.6)
    fair = sum(1 for r in results if 0.2 <= r["token_overlap"] < 0.4)
    poor = sum(1 for r in results if r["token_overlap"] < 0.2)
    
    print(f"  🌟 Excellent (>60% sim):   {excellent}/{len(results)} ({100*excellent/len(results):.0f}%)")
    print(f"  ✓  Good (40-60% sim):       {good}/{len(results)} ({100*good/len(results):.0f}%)")
    print(f"  △  Fair (20-40% sim):       {fair}/{len(results)} ({100*fair/len(results):.0f}%)")
    print(f"  ✗  Poor (<20% sim):         {poor}/{len(results)} ({100*poor/len(results):.0f}%)")
    
    # Sample outputs
    print(f"\n📝 SAMPLE OUTPUTS (first 3):")
    for i, r in enumerate(results[:3]):
        print(f"\n  [{i+1}] {r['question']}")
        print(f"      Expected: {r['expected_preview']}...")
        print(f"      Generated: {r['generated_preview']}...")
        print(f"      Similarity: {r['token_overlap']:.1%}")


def main():
    parser = argparse.ArgumentParser(description="Quick local model evaluation")
    parser.add_argument("adapter_path", help="Path to LoRA adapter or merged GGUF model")
    parser.add_argument("--samples", "-n", type=int, default=20,
                        help="Number of validation samples to evaluate (default: 20)")
    parser.add_argument("--spec", "-s", help="Subject spec JSON")
    parser.add_argument("--val-data", help="Validation JSONL (auto-detected if not provided)")
    
    args = parser.parse_args()
    
    adapter_path = Path(args.adapter_path)
    if not adapter_path.exists():
        print(f"Error: {adapter_path} does not exist")
        sys.exit(1)
    
    # Find validation set
    val_path = None
    if args.val_data:
        val_path = args.val_data
    else:
        # Try to auto-detect
        npc_key = adapter_path.name
        val_candidates = [
            PROJECT_ROOT / "datasets" / npc_key / "notebooklm" / "validation.jsonl",
            PROJECT_ROOT / "datasets" / npc_key / "ollama" / "validation.jsonl",
            PROJECT_ROOT / "datasets" / "chemistry_instructor" / "notebooklm" / "validation.jsonl",
        ]
        for vc in val_candidates:
            if vc.exists():
                val_path = str(vc)
                break
    
    if not val_path or not Path(val_path).exists():
        print(f"Error: Validation set not found. Tried:")
        print(f"  - {val_candidates[0]}")
        print(f"Use --val-data to specify manually")
        sys.exit(1)
    
    # Load validation set
    print(f"[eval] Loading validation set: {val_path}")
    val_set = load_validation_set(val_path, limit=args.samples)
    print(f"[eval] Loaded {len(val_set)} examples")
    
    # Load spec if provided
    spec = None
    if args.spec:
        with open(args.spec) as f:
            spec = json.load(f)
    
    # Evaluate
    results = evaluate_model_local(str(adapter_path), val_set, spec, max_samples=args.samples)
    
    # Report
    if results:
        report(results, spec)


if __name__ == "__main__":
    main()
