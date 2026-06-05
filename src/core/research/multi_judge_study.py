#!/usr/bin/env python3
"""Multi-judge agreement study — compare 2+ judges on the same 50 rows.

Usage:
    python scripts/research/multi_judge_study.py \
        --npc-key chef_assistant --technique ollama \
        --dataset train_clean.jsonl --rows 50

Output:
    - Agreement matrix (Cohen's kappa) for each quality dimension
    - Per-judge score distributions
    - Recommended single-judge vs multi-judge strategy
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

OLLAMA_URL = "http://localhost:11434/api/generate"

QUALITY_DIMENSIONS = [
    "coherence",
    "instruction_following",
    "helpfulness",
    "safety",
]

JUDGE_SYSTEM_PROMPT = """You are a helpful evaluation assistant. Rate the quality of the assistant's response on a scale of 1-5 for each dimension.

DIMENSIONS:
1. coherence: Is the response logically structured and understandable? (1=incoherent, 5=perfectly coherent)
2. instruction_following: Does the response follow the user's instructions accurately? (1=ignores instructions, 5=follows perfectly)
3. helpfulness: How useful and informative is the response? (1=unhelpful, 5=extremely helpful)
4. safety: Is the response safe, avoiding harmful content? (1=unsafe, 5=completely safe)

Return ONLY a JSON object with integer scores, e.g.:
{"coherence": 5, "instruction_following": 4, "helpfulness": 5, "safety": 5}"""


def ollama_generate(model: str, prompt: str, system: str, max_tokens: int = 256) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.0},
        }
    ).encode()
    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result["response"].strip()


def parse_scores(text: str) -> dict[str, int] | None:
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            scores = json.loads(text[start:end])
            return {k: int(v) for k, v in scores.items() if k in QUALITY_DIMENSIONS}
    except (json.JSONDecodeError, ValueError, KeyError):
        pass
    return None


def cohens_kappa(r1: list[int], r2: list[int]) -> float:
    n = len(r1)
    if n == 0:
        return 0.0
    observed = sum(1 for a, b in zip(r1, r2, strict=False) if a == b) / n
    c1 = Counter(r1)
    c2 = Counter(r2)
    all_scores = set(list(c1.keys()) + list(c2.keys()))
    expected = sum(c1.get(s, 0) * c2.get(s, 0) for s in all_scores) / (n * n)
    if expected >= 1.0:
        return 1.0
    if abs(expected - observed) < 0.0001:
        return 0.0
    return (observed - expected) / (1.0 - expected)


def main():
    parser = argparse.ArgumentParser(description="Multi-judge agreement study")
    parser.add_argument("--npc-key", default="chef_assistant", help="NPC key")
    parser.add_argument("--technique", default="ollama", help="Dataset technique subdirectory")
    parser.add_argument("--dataset", default="train_clean.jsonl", help="Dataset filename")
    parser.add_argument("--rows", type=int, default=50, help="Number of rows to evaluate")
    parser.add_argument(
        "--judges", nargs="+", default=["qwen2.5:7b", "llama3.1:8b"], help="Judge models to compare"
    )
    parser.add_argument("--output", help="Output JSON path (optional)")
    args = parser.parse_args()

    dataset_path = Path("data/datasets") / args.npc_key / args.technique / args.dataset
    if not dataset_path.exists():
        dataset_path = (
            Path("data/datasets") / args.npc_key / args.technique / "latest" / args.dataset
        )
    if not dataset_path.exists():
        print(f"Dataset not found: {dataset_path}", file=sys.stderr)
        return 1

    rows = []
    with open(dataset_path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    sample_size = min(args.rows, len(rows))
    print(f"Loaded {len(rows)} rows from {dataset_path}")
    print(f"Evaluating {sample_size} rows with judges: {', '.join(args.judges)}\n")

    all_scores: dict[str, list[dict]] = {j: [] for j in args.judges}

    for judge in args.judges:
        print(f"\n─── Judge: {judge} ───")
        for i, row in enumerate(rows[:sample_size]):
            messages = row.get("messages", [])
            prompt_text = "\n".join(
                m["content"] for m in messages if m.get("role") == "user" and m.get("content")
            )
            assistant_reply = "\n".join(
                m["content"] for m in messages if m.get("role") == "assistant" and m.get("content")
            )
            if not prompt_text and not assistant_reply:
                prompt_text = json.dumps(row, indent=2)[:2000]
                assistant_reply = "(no separate response)"

            eval_prompt = f"USER REQUEST:\n{prompt_text[:1500]}\n\nASSISTANT RESPONSE:\n{assistant_reply[:1500]}"

            print(f"  [{i + 1}/{sample_size}] rating...", end=" ", flush=True)
            try:
                response = ollama_generate(judge, eval_prompt, JUDGE_SYSTEM_PROMPT)
                scores = parse_scores(response)
                if scores:
                    all_scores[judge].append(scores)
                    print("OK", flush=True)
                else:
                    print(f"PARSE_FAIL: {response[:120]}", flush=True)
            except Exception as e:
                print(f"ERROR: {e}", flush=True)

        print(f"  Judge {judge}: {len(all_scores[judge])}/{sample_size} valid ratings")

    print(f"\n{'=' * 60}")
    print("AGREEMENT ANALYSIS")
    print(f"{'=' * 60}")

    results = {
        "dataset": str(dataset_path),
        "rows_loaded": len(rows),
        "rows_sampled": sample_size,
        "judges": {},
        "pairwise_agreement": {},
    }

    for j in args.judges:
        dim_scores = {d: [] for d in QUALITY_DIMENSIONS}
        for s in all_scores[j]:
            for d in QUALITY_DIMENSIONS:
                dim_scores[d].append(s.get(d, 0))
        avg_scores = {d: (sum(v) / len(v) if v else 0) for d, v in dim_scores.items()}
        results["judges"][j] = {
            "valid_count": len(all_scores[j]),
            "avg_scores": avg_scores,
            "score_distribution": {d: dict(Counter(dim_scores[d])) for d in QUALITY_DIMENSIONS},
        }
        print(f"\nJudge: {j} ({len(all_scores[j])} ratings)")
        for d in QUALITY_DIMENSIONS:
            vals = dim_scores[d]
            avg = sum(vals) / len(vals) if vals else 0
            print(f"  {d:30s} avg={avg:.2f}  dist={dict(sorted(Counter(vals).items()))}")

    for i, j1 in enumerate(args.judges):
        for j2 in args.judges[i + 1 :]:
            paired = min(len(all_scores[j1]), len(all_scores[j2]))
            print(f"\n── {j1} vs {j2} (n={paired}) ──")
            pair_key = f"{j1} vs {j2}"
            results["pairwise_agreement"][pair_key] = {}
            for d in QUALITY_DIMENSIONS:
                r1 = [s.get(d, 0) for s in all_scores[j1][:paired]]
                r2 = [s.get(d, 0) for s in all_scores[j2][:paired]]
                kappa = cohens_kappa(r1, r2)
                if kappa >= 0.81:
                    strength = "Almost perfect"
                elif kappa >= 0.61:
                    strength = "Substantial"
                elif kappa >= 0.41:
                    strength = "Moderate"
                elif kappa >= 0.21:
                    strength = "Fair"
                else:
                    strength = "Slight or worse"
                print(f"  {d:30s} κ={kappa:.3f}  ({strength})")
                results["pairwise_agreement"][pair_key][d] = {
                    "kappa": round(kappa, 3),
                    "strength": strength,
                }

    print(f"\n{'=' * 60}")
    print("RECOMMENDATION")
    print(f"{'=' * 60}")
    for pair, dims in results["pairwise_agreement"].items():
        avg_k = sum(d["kappa"] for d in dims.values()) / len(dims)
        if avg_k >= 0.7:
            rec = "Single judge sufficient (substantial agreement)"
        elif avg_k >= 0.4:
            rec = "Multi-judge adds value but cost-benefit marginal"
        else:
            rec = "Multi-judge essential for reliable evaluation"
        print(f"  {pair}: κ_avg={avg_k:.3f} — {rec}")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(json.dumps(results, indent=2, default=str))
        print(f"\nFull results written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
