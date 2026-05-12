#!/usr/bin/env python3
"""
track_eval_results.py — Store and track model evaluation results in Supabase

Usage:
    python scripts/track_eval_results.py \\
        --npc-key chemistry_instructor \\
        --model exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-q4_k_m.gguf \\
        --win-rate 0.75 \\
        --avg-quality 42.5 \\
        --notes "Initial Colab training - looks good"
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def track_result(npc_key, model_path, win_rate=None, avg_quality=None, 
                 notes="", val_loss=None, test_loss=None, metrics=None, metadata=None,
                 results_file=None):
    """Store summary evaluation result in Supabase."""
    
    import os
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        print("⚠️  Supabase credentials not configured. Saving locally.")
        save_local_result(npc_key, model_path, win_rate, avg_quality, notes, val_loss, test_loss,
                          results_file=results_file, metrics=metrics, metadata=metadata)
        return False
    
    try:
        from supabase import create_client, Client
        client: Client = create_client(url, key)
        
        result = {
            "npc_id": npc_key,
            "test_name": f"Eval Run {datetime.now().strftime('%Y%m%d_%H%M')}",
            "test_type": "summary",
            "prompt_text": "summary",
            "response_text": notes or "summary",
            "score": win_rate or avg_quality or 0.0,
            "metrics": {
                "win_rate": win_rate,
                "avg_quality": avg_quality,
                "val_loss": val_loss,
                "test_loss": test_loss,
                **(metrics or {})
            },
            "metadata": {
                "model_path": str(model_path),
                "notes": notes,
                **(metadata or {})
            },
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        client.table("test_results").insert(result).execute()
        print("✓ Summary results saved to Supabase")
        return True
    except Exception as e:
        print(f"Error saving to Supabase: {e}")
        save_local_result(npc_key, model_path, win_rate, avg_quality, notes, val_loss, test_loss,
                          results_file=results_file, metrics=metrics, metadata=metadata)
        return False


def track_per_example_result(npc_key, test_name, prompt, response, expected=None, score=None, metrics=None, metadata=None):
    """Store a single per-example test result in Supabase."""
    import os
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        return False
        
    try:
        from supabase import create_client, Client
        client: Client = create_client(url, key)
        
        result = {
            "npc_id": npc_key,
            "test_name": test_name,
            "test_type": "example",
            "prompt_text": prompt,
            "response_text": response,
            "expected_response": expected,
            "score": score,
            "metrics": metrics or {},
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        client.table("test_results").insert(result).execute()
        return True
    except Exception as e:
        print(f"Error tracking example: {e}")
        return False


def save_local_result(npc_key, model_path, win_rate=None, avg_quality=None, 
                      notes="", val_loss=None, test_loss=None, results_file=None,
                      metrics=None, metadata=None):
    """Save evaluation result locally."""
    if results_file is None:
        from _config import paths
        results_file = paths.eval_results_path()
    results_file = Path(results_file)
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    result = {
        "npc_key": npc_key,
        "model_path": str(model_path),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "win_rate": win_rate,
        "avg_quality": avg_quality,
        "val_loss": val_loss,
        "test_loss": test_loss,
        "notes": notes,
        "metrics": metrics or {},
        "metadata": metadata or {},
    }
    
    with open(results_file, "a") as f:
        f.write(json.dumps(result) + "\n")
    
    print(f"✓ Results saved locally to: {results_file}")


def show_results_history(npc_key=None, results_file=None):
    """Show historical results."""
    if results_file is None:
        from _config import paths
        results_file = paths.eval_results_path()
    results_file = Path(results_file)
    
    if not results_file.exists():
        print("No evaluation results found")
        return
    
    results = []
    with open(results_file) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    
    # Filter by npc_key if provided
    if npc_key:
        results = [r for r in results if r.get("npc_key") == npc_key]
    
    if not results:
        print("No results found")
        return
    
    print("\n" + "="*80)
    print(f"  EVALUATION HISTORY ({len(results)} results)")
    print("="*80)
    
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['npc_key']} - {r['timestamp'][:19]}")
        if r.get("win_rate") is not None:
            print(f"    Win Rate: {r['win_rate']:.0%}")
        if r.get("avg_quality") is not None:
            print(f"    Avg Quality: {r['avg_quality']:.1f}")
        if r.get("val_loss") is not None:
            print(f"    Val Loss: {r['val_loss']:.4f}")
        if r.get("test_loss") is not None:
            print(f"    Test Loss: {r['test_loss']:.4f}")
        if r.get("notes"):
            print(f"    Notes: {r['notes']}")


def main():
    parser = argparse.ArgumentParser(description="Track model evaluation results")
    
    # Actions
    parser.add_argument("--track", action="store_true", help="Record new evaluation result")
    parser.add_argument("--show", action="store_true", help="Show evaluation history")
    
    # For tracking
    parser.add_argument("--npc-key", help="NPC key (e.g., chemistry_instructor)")
    parser.add_argument("--model", help="Model GGUF path")
    parser.add_argument("--win-rate", type=float, help="Win rate vs baseline (0-1)")
    parser.add_argument("--avg-quality", type=float, help="Average quality score")
    parser.add_argument("--val-loss", type=float, help="Validation loss")
    parser.add_argument("--test-loss", type=float, help="Test loss")
    parser.add_argument("--notes", default="", help="Notes about this run")
    parser.add_argument("--results-file", help="Custom results file path (default: eval/results/eval_results.jsonl)")
    
    args = parser.parse_args()
    
    if not args.track and not args.show:
        parser.print_help()
        return
    
    if args.track:
        if not args.npc_key:
            print("Error: --npc-key required for tracking")
            sys.exit(1)
        
        track_result(
            args.npc_key,
            args.model or "unknown",
            win_rate=args.win_rate,
            avg_quality=args.avg_quality,
            val_loss=args.val_loss,
            test_loss=args.test_loss,
            notes=args.notes,
            results_file=args.results_file,
        )
    
    if args.show:
        show_results_history(args.npc_key, results_file=args.results_file)


if __name__ == "__main__":
    main()
