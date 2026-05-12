#!/usr/bin/env python3
"""
batch_export.py — Batch export all trained NPCs to GGUF without reloading the base model.

Loads the base model once, then iterates all NPCs with trained LoRA adapters,
exporting each to the correct GGUF path.

Usage:
    python scripts/batch_export.py [--quantization q4_k_m] [--model unsloth/Llama-3.2-3B-Instruct-bnb-4bit]
    python scripts/batch_export.py --skip-f16    # only export quantized variant
    python scripts/batch_export.py --npc chemistry_instructor,bible_instructor  # specific NPCs only
"""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths


def _export_one(model, tokenizer, npc_key, model_id, quant, skip_f16=False):
    """Export one NPC's LoRA adapter to GGUF without reloading the base model.

    Returns True on success, False on failure.
    """
    try:
        _, output_dir = paths.resolve_adapter_dir(npc_key)
    except FileNotFoundError:
        print(f"  \u26a0  Skipping '{npc_key}': No adapter found")
        return False
    adapter_config = output_dir / "adapter_config.json"

    print(f"\n{'=' * 60}")
    print(f"  Exporting: {npc_key}")
    print(f"{'=' * 60}")

    from unsloth import save as unsloth_save
    from peft import PeftModel
    import torch
    import types

    # Load LoRA on top of existing base model
    print(f"  Loading LoRA adapter from: {output_dir}")
    peft_model = PeftModel.from_pretrained(model, str(output_dir), is_trainable=False)
    # Re-bind save_pretrained_gguf to the PeftModel wrapper
    peft_model.save_pretrained_gguf = types.MethodType(
        unsloth_save.unsloth_save_pretrained_gguf, peft_model,
    )

    # Export quantized GGUF
    gguf_path = paths.export_gguf_path(npc_key, model_id, quant)
    gguf_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix=f"gguf_{npc_key}_") as tmpdir:
        print(f"  Generating GGUF ({quant})...")
        t0 = time.time()
        peft_model.save_pretrained_gguf(
            tmpdir,
            tokenizer=tokenizer,
            quantization_method=quant,
        )
        gguf_files = sorted(Path(tmpdir).glob("*.gguf"))
        if not gguf_files:
            print(f"  \u2717  No GGUF file generated for '{npc_key}'")
            return False
        shutil.move(str(gguf_files[0]), str(gguf_path))
        elapsed = time.time() - t0
        size_gb = gguf_path.stat().st_size / (1024 * 1024 * 1024)
        print(f"  \u2713  {gguf_path.name} ({size_gb:.2f} GB) in {elapsed:.0f}s")

    # Export f16 variant
    if not skip_f16:
        f16_path = paths.export_gguf_path(npc_key, model_id, "f16")
        f16_path.parent.mkdir(parents=True, exist_ok=True)

        # Skip if f16 already exists and is newer than adapter
        if f16_path.exists() and f16_path.stat().st_mtime > adapter_config.stat().st_mtime:
            print(f"  ~  f16 already up-to-date, skipping")
        else:
            with tempfile.TemporaryDirectory(prefix=f"gguf_{npc_key}_f16_") as tmpdir:
                print(f"  Generating GGUF (f16)...")
                t0 = time.time()
                peft_model.save_pretrained_gguf(
                    tmpdir,
                    tokenizer=tokenizer,
                    quantization_method="f16",
                )
                gguf_files = sorted(Path(tmpdir).glob("*.gguf"))
                if gguf_files:
                    shutil.move(str(gguf_files[0]), str(f16_path))
                    elapsed = time.time() - t0
                    size_mb = f16_path.stat().st_size / (1024 * 1024)
                    print(f"  \u2713  {f16_path.name} ({size_mb:.0f} MB) in {elapsed:.0f}s")

    # Free LoRA memory
    del peft_model
    torch.cuda.empty_cache()
    return True


def find_trained_npcs():
    """Discover all NPCs that have trained adapters."""
    npcs = []
    outputs_dir = paths.output_root()
    if not outputs_dir.exists():
        return npcs
    for entry in sorted(outputs_dir.iterdir()):
        if not entry.is_dir() or entry.name == "colab":
            continue
        try:
            _, adapter_dir = paths.resolve_adapter_dir(str(entry))
            npcs.append(adapter_dir)
        except FileNotFoundError:
            continue
    return npcs


def main():
    parser = argparse.ArgumentParser(
        description="Batch export all trained NPCs to GGUF without reloading the base model"
    )
    parser.add_argument("--quantization", default="q4_k_m",
                        help="GGUF quantization method (default: q4_k_m)")
    parser.add_argument("--model", "-m",
                        help="Base model ID (default: auto-detect from first NPC)")
    parser.add_argument("--skip-f16", action="store_true",
                        help="Skip exporting f16 variants")
    parser.add_argument("--npc",
                        help="Comma-separated list of NPC keys to export (default: all trained)")
    args = parser.parse_args()

    # ── Discover NPCs to export ─────────────────────────────────────────────
    if args.npc:
        npc_keys = [k.strip() for k in args.npc.split(",")]
    else:
        npc_keys = find_trained_npcs()

    if not npc_keys:
        print("Error: No trained NPCs found.")
        print(f"Looked in: {paths.output_root()}")
        print("Train some first with: python scripts/train.py subjects/<npc>.json --from-spec --preset fast-3b")
        sys.exit(1)

    print(f"Found {len(npc_keys)} trained NPC(s): {', '.join(npc_keys)}")

    # ── Auto-detect model ID ────────────────────────────────────────────────
    model_id = args.model
    if model_id is None:
        # Try auto-detecting from first NPC's adapter config
        _, first_output = paths.resolve_adapter_dir(npc_keys[0])
        adapter_config = first_output / "adapter_config.json"
        if adapter_config.exists():
            with open(adapter_config) as f:
                cfg = json.load(f)
            model_id = cfg.get("base_model_name_or_path",
                              "unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
        else:
            model_id = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
        print(f"Auto-detected model: {model_id}")

    # ── Load base model ONCE ────────────────────────────────────────────────
    print(f"\nLoading base model: {model_id}")
    print("This may take a few minutes (downloading if not cached)...")
    t0 = time.time()

    from unsloth import FastLanguageModel
    import torch

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_id,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )
    print(f"  Model loaded in {time.time() - t0:.0f}s")

    # ── Export each NPC ─────────────────────────────────────────────────────
    success = 0
    failed = 0
    for npc_key in npc_keys:
        ok = _export_one(model, tokenizer, npc_key, model_id, args.quantization, args.skip_f16)
        if ok:
            success += 1
        else:
            failed += 1

    # ── Summary ─────────────────────────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  BATCH EXPORT COMPLETE")
    print(f"  Successful: {success}")
    print(f"  Failed:     {failed}")
    print(f"  Total:      {len(npc_keys)}")
    print(f"{'=' * 60}")

    if success > 0:
        print(f"\nExported GGUF files:")
        for npc_key in npc_keys:
            if paths.output_dir(npc_key).exists():
                q_path = paths.export_gguf_path(npc_key, model_id, args.quantization)
                if q_path.exists():
                    s = q_path.stat().st_size / (1024 * 1024 * 1024)
                    print(f"  \u2713  {q_path} ({s:.2f} GB)")
                f16_path = paths.export_gguf_path(npc_key, model_id, "f16")
                if f16_path.exists():
                    s = f16_path.stat().st_size / (1024 * 1024)
                    print(f"  \u2713  {f16_path.name} ({s:.0f} MB)")


if __name__ == "__main__":
    main()
