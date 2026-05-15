#!/usr/bin/env python3
"""
test_chemistry_instructor.py — Quick test script for chemistry instructor model

Tests the LoRA adapter by checking:
1. Response quality on training examples
2. Whether it follows personality constraints
3. Semantic similarity to expected outputs
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from _config import paths


def load_training_data():
    """Load training and validation data."""
    train_path = paths.dataset_train_path("chemistry_instructor", "onyx")
    val_path = paths.dataset_val_path("chemistry_instructor", "onyx")
    
    train_data = []
    if train_path.exists():
        with open(train_path) as f:
            for line in f:
                if line.strip():
                    train_data.append(json.loads(line))
    
    val_data = []
    if val_path.exists():
        with open(val_path) as f:
            for line in f:
                if line.strip():
                    val_data.append(json.loads(line))
    
    return train_data, val_data


def extract_qa_from_messages(messages):
    """Extract user question and assistant response."""
    user_q = None
    assistant_resp = None
    
    for msg in messages:
        if msg["role"] == "user":
            user_q = msg["content"]
        elif msg["role"] == "assistant":
            assistant_resp = msg["content"]
    
    return user_q, assistant_resp


def analyze_response_quality(response):
    """Analyze quality of a response."""
    if not response:
        return {}
    
    # Word/sentence count
    words = response.split()
    sentences = [s.strip() for s in re.split(r'[.!?]+', response) if s.strip()]
    
    # Unique words (diversity)
    unique_words = len(set(w.lower() for w in words))
    ttr = unique_words / len(words) if words else 0  # Type-token ratio
    
    # Check for issues
    has_ai_claim = any(p in response.lower() for p in [
        "i am an ai", "i'm an ai", "artificial intelligence", "as an ai"
    ])
    
    has_think_tags = "<｜end▁of▁thinking｜>" in response or "<think>" in response
    
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "diversity_ttr": round(ttr, 3),
        "has_ai_claim": has_ai_claim,
        "has_think_tags": has_think_tags,
    }


def print_dataset_summary():
    """Print summary of training/validation data."""
    train_data, val_data = load_training_data()
    
    print("\n" + "="*70)
    print("  CHEMISTRY INSTRUCTOR DATASET SUMMARY")
    print("="*70)
    
    print(f"\n📚 Data Splits:")
    print(f"  Training examples:    {len(train_data)}")
    print(f"  Validation examples:  {len(val_data)}")
    
    if train_data:
        print(f"\n📝 Sample Training Examples:")
        for i, example in enumerate(train_data[:3]):
            msgs = example.get("messages", [])
            user_q, asst = extract_qa_from_messages(msgs)
            if user_q and asst:
                print(f"\n  [{i+1}] Q: {user_q[:80]}")
                print(f"      A: {asst[:80]}...")
    
    if val_data:
        print(f"\n✓ Sample Validation Examples (held-out test set):")
        for i, example in enumerate(val_data[:3]):
            msgs = example.get("messages", [])
            user_q, asst = extract_qa_from_messages(msgs)
            if user_q and asst:
                print(f"\n  [{i+1}] Q: {user_q[:80]}")
                print(f"      A: {asst[:80]}...")
    
    # Analysis
    print(f"\n📊 Response Quality in Training Data:")
    response_lengths = []
    for example in train_data:
        msgs = example.get("messages", [])
        _, asst = extract_qa_from_messages(msgs)
        if asst:
            words = len(asst.split())
            response_lengths.append(words)
    
    if response_lengths:
        avg_len = sum(response_lengths) / len(response_lengths)
        print(f"  Average response length: {avg_len:.0f} words")
        print(f"  Min length: {min(response_lengths)}, Max length: {max(response_lengths)}")


def main():
    print_dataset_summary()
    
    print("\n" + "="*70)
    print("  NEXT STEPS FOR TESTING YOUR MODEL")
    print("="*70)
    
    print("""
1. CHECK TRAINING PROGRESS
   └─ Training loss should have decreased during Colab training
   └─ Check Colab notebook output for loss curves
   
2. TEST WITH QUICK_EVAL.PY (requires llama-cpp-python)
   └─ pip install llama-cpp-python
   └─ python scripts/quick_eval.py \\
        outputs/chemistry_instructor \\
        --samples 20
   
3. TEST IN UNITY DIRECTLY
   └─ Load the GGUF file: chemistry_instructor-lora.f16.gguf
   └─ Test with chemistry questions in-game
   └─ Check Console for response quality
   
4. METRICS TO TRACK
   ✓ Response length (should match training data ~80-120 words)
   ✓ Diversity (unique words / total words, target: 0.4-0.7)
   ✓ No AI disclaimers (model shouldn't say "I'm an AI")
   ✓ Semantic accuracy (relevant to chemistry domain)
   ✓ Instruction following (personality traits)
   
5. COMPARE MODELS OVER TIME
   ├─ Train multiple iterations (different hyperparameters)
   ├─ Export each as GGUF with unique names:
   │  ├─ chemistry_instructor_v1.gguf
   │  ├─ chemistry_instructor_v2.gguf
   │  └─ chemistry_instructor_v3.gguf
   └─ Use quick_eval.py on each to see improvement
   
6. ITERATIVE IMPROVEMENT
   ├─ Analyze failure cases from evaluation
   ├─ Adjust training data if needed
   ├─ Re-train with better parameters
   └─ Re-export and test again
""")


if __name__ == "__main__":
    main()
