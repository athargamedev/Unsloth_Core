#!/usr/bin/env python3
"""
export.py — Export trained LoRA adapter to GGUF for Unity/LLMUnity.

Usage:
    # New style (recommended):
    python scripts/export.py chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit

    # Legacy style (still supported):
    python scripts/export.py outputs/my_model [--quantization q4_k_m]
"""

import argparse
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths


def _export_gguf_file(model, tokenizer, model_id, quantization, output_path):
    """Export to GGUF using a temp dir, then move the generated file to output_path.
    
    Unsloth's save_pretrained_gguf creates a directory; this helper
    extracts the single .gguf file from that directory and renames it.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gguf_export_") as tmpdir:
        print(f"  Generating GGUF in temporary directory...")
        model.save_pretrained_gguf(
            tmpdir,
            tokenizer=tokenizer,
            quantization_method=quantization,
        )
        # Find the generated GGUF file — Unsloth may create it in
        # tmpdir itself OR in a parallel {tmpdir}_gguf/ directory.
        gguf_files = sorted(Path(tmpdir).rglob("*.gguf"))
        # Also check the parent-relative _gguf sibling directory
        sibling = Path(f"{tmpdir}_gguf")
        if not gguf_files and sibling.exists():
            gguf_files = sorted(sibling.rglob("*.gguf"))
        if not gguf_files:
            print(f"Error: No GGUF file generated in {tmpdir}")
            print(f"Directory contents: {list(Path(tmpdir).iterdir())}")
            if sibling.exists():
                print(f"Sibling _gguf directory contents: {list(sibling.iterdir())}")
            sys.exit(1)
        generated = gguf_files[0]
        # Move to final destination with our naming convention
        shutil.move(str(generated), str(output_path))

    file_size = output_path.stat().st_size / (1024 * 1024 * 1024)
    print(f"  → {output_path} ({file_size:.2f} GB)")


def write_manifest(npc_key: str, model_id: str, quantizations: list[str],
                   gguf_files: list[Path], output_dir: Path) -> dict:
    """Write manifest.json to the export directory with provenance metadata."""
    from _config import paths
    import json
    from datetime import datetime, timezone

    manifest_path = paths.export_manifest_path(npc_key)
    manifest = {
        "npc_key": npc_key,
        "model_id": model_id,
        "model_short": paths.model_short_name(model_id),
        "quantizations": quantizations,
        "gguf_files": [f.name for f in gguf_files],
        "exported_at": datetime.now(timezone.utc).isoformat(),
    }

    # Try to get npc_name from subject spec
    subjects_dir = output_dir.parent.parent / "subjects"
    spec_path = subjects_dir / f"{npc_key}.json"
    if spec_path.exists():
        try:
            with open(spec_path) as f:
                spec = json.load(f)
                manifest["npc_name"] = spec.get("npc_name", npc_key)
        except Exception:
            manifest["npc_name"] = npc_key
    else:
        manifest["npc_name"] = npc_key

    # Try to get training provenance from latest run
    try:
        latest = paths.latest_run_dir(npc_key)
        if latest and (latest / "metrics.json").exists():
            with open(latest / "metrics.json") as f:
                metrics = json.load(f)
            manifest["run_id"] = metrics.get("run_id")
            manifest["trained_at"] = metrics.get("timestamp")
            train_loss = metrics.get("training_loss")
            if train_loss is not None:
                import math
                manifest["training_loss"] = round(train_loss, 4)
                manifest["eval_perplexity"] = round(math.exp(train_loss) if train_loss > 0 else 999, 2)
    except Exception:
        pass

    # Write manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"  → Manifest: {manifest_path}")

    return manifest


def main():
    parser = argparse.ArgumentParser(description="Export trained LoRA to GGUF")
    parser.add_argument(
        "npc_key_or_dir",
        help="NPC key (e.g., chemistry_instructor) or path to training output directory",
    )
    parser.add_argument(
        "--quantization",
        default="q4_k_m",
        help="GGUF quantization method (default: q4_k_m)",
    )
    parser.add_argument(
        "--model", "-m",
        help="Base model ID (default: auto-detect from adapter_config.json)",
    )
    parser.add_argument(
        "--output-dir",
        help="Override output directory path (default: auto-detected from npc_key)",
    )
    parser.add_argument(
        "--skip-f16", action="store_true",
        help="Skip exporting the f16 variant",
    )
    args = parser.parse_args()

    # ── Determine output directory ──────────────────────────────────────────
    input_path = Path(args.npc_key_or_dir)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    elif input_path.exists() and input_path.is_dir() and not input_path.name.startswith("outputs"):
        # Direct path to a training output (legacy mode)
        output_dir = input_path
    else:
        # NPC key mode
        npc_key = args.npc_key_or_dir
        output_dir = paths.output_dir(npc_key)
        if not output_dir.exists():
            print(f"Error: Output directory not found: {output_dir}")
            print(f"Train the NPC first with: python scripts/train.py subjects/{npc_key}.json --from-spec --preset fast-3b")
            sys.exit(1)

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        sys.exit(1)

    # ── Derive metadata ─────────────────────────────────────────────────────
    npc_key = output_dir.name

    # Auto-detect model ID from adapter_config if not provided
    model_id = args.model
    if model_id is None:
        adapter_config = output_dir / "adapter_config.json"
        if adapter_config.exists():
            with open(adapter_config) as f:
                cfg = json.load(f)
            model_id = cfg.get(
                "base_model_name_or_path",
                "unsloth/Llama-3.2-3B-Instruct-bnb-4bit",
            )
        else:
            model_id = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"

    print(f"Exporting LoRA from: {output_dir}")
    print(f"  NPC key:       {npc_key}")
    print(f"  Model ID:      {model_id}")
    print(f"  Quantization:  {args.quantization}")

    # ── Load model ──────────────────────────────────────────────────────────
    from unsloth import FastLanguageModel, save as unsloth_save
    from peft import PeftModel
    import torch
    import types

    print(f"\nLoading model...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_id,
        max_seq_length=2048,
        dtype=None,
        load_in_4bit=True,
    )

    # ── Load LoRA adapter (if present) ──────────────────────────────────────
    adapter_path = output_dir / "adapter_config.json"
    if adapter_path.exists():
        print(f"  Loading LoRA adapter from: {output_dir}")
        model = PeftModel.from_pretrained(model, str(output_dir), is_trainable=False)
        # Re-bind save_pretrained_gguf to the PeftModel wrapper
        model.save_pretrained_gguf = types.MethodType(
            unsloth_save.unsloth_save_pretrained_gguf, model,
        )

    # ── Export quantized GGUF ───────────────────────────────────────────────
    gguf_path = paths.export_gguf_path(npc_key, model_id, args.quantization)
    _export_gguf_file(model, tokenizer, model_id, args.quantization, gguf_path)

    # ── Also export f16 GGUF for deployment use ─────────────────────────────
    if not args.skip_f16:
        f16_path = paths.export_gguf_path(npc_key, model_id, "f16")
        _export_gguf_file(model, tokenizer, model_id, "f16", f16_path)

    # ── Write manifest.json ────────────────────────────────────────────────
    gguf_files = [gguf_path]
    quantizations = [args.quantization]
    if not args.skip_f16:
        gguf_files.append(f16_path)
        quantizations.append("f16")
    write_manifest(npc_key, model_id, quantizations, gguf_files, output_dir)

    print(f"\nExport complete!")
    print(f"  GGUF (quant): {gguf_path}")
    if not args.skip_f16:
        print(f"  GGUF (f16):   {f16_path}")


if __name__ == "__main__":
    main()
