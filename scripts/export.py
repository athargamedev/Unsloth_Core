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
import contextlib
import json
import math
import os
import shutil
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths


def _status_path(npc_key: str) -> Path:
    return paths.export_dir(npc_key) / "export_status.json"


def _write_status(npc_key: str, **fields):
    sp = _status_path(npc_key)
    sp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "npc_key": npc_key,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if sp.exists():
        with contextlib.suppress(Exception):
            payload.update(json.loads(sp.read_text()))
    payload.update(fields)
    sp.write_text(json.dumps(payload, indent=2))


class ExportTimeoutError(RuntimeError):
    pass


@contextlib.contextmanager
def _time_limit(seconds: int | None, message: str):
    if not seconds or seconds <= 0:
        yield
        return

    def _handler(_signum, _frame):
        raise ExportTimeoutError(message)

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _heartbeat(stop_event: threading.Event, npc_key: str, substep: str, interval_s: int = 20):
    started = time.time()
    while not stop_event.wait(interval_s):
        elapsed = int(time.time() - started)
        msg = f"  [heartbeat] {substep} running ({elapsed}s elapsed)"
        print(msg)
        _write_status(
            npc_key,
            state="running",
            substep=substep,
            last_heartbeat=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            elapsed_seconds=elapsed,
            pid=os.getpid(),
        )


def _export_gguf_file(model, tokenizer, model_id, quantization, output_path, *, npc_key: str, substep_timeout: int | None = None):
    """Export to GGUF using a temp dir, then move the generated file to output_path.
    
    Unsloth's save_pretrained_gguf creates a directory; this helper
    extracts the single .gguf file from that directory and renames it.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gguf_export_") as tmpdir:
        print(f"  Generating GGUF in temporary directory...")
        _write_status(npc_key, state="running", substep=f"export_{quantization}", temp_dir=tmpdir)
        hb_stop = threading.Event()
        hb = threading.Thread(target=_heartbeat, args=(hb_stop, npc_key, f"export_{quantization}"), daemon=True)
        hb.start()
        try:
            with _time_limit(substep_timeout, f"Timed out exporting {quantization} GGUF after {substep_timeout}s"):
                model.save_pretrained_gguf(
                    tmpdir,
                    tokenizer=tokenizer,
                    quantization_method=quantization,
                )
        finally:
            hb_stop.set()
            hb.join(timeout=1)
        # Find the generated GGUF file — Unsloth may create it in
        # tmpdir itself OR in a parallel {tmpdir}_gguf/ directory.
        gguf_files = sorted(Path(tmpdir).rglob("*.gguf"))
        # Also check the parent-relative _gguf sibling directory
        sibling = Path(f"{tmpdir}_gguf")
        if not gguf_files and sibling.exists():
            gguf_files = sorted(sibling.rglob("*.gguf"))
        if not gguf_files:
            _write_status(npc_key, state="failed", substep=f"export_{quantization}", error_summary="No GGUF generated")
            print(f"Error: No GGUF file generated in {tmpdir}")
            print(f"Directory contents: {list(Path(tmpdir).iterdir())}")
            if sibling.exists():
                print(f"Sibling _gguf directory contents: {list(sibling.iterdir())}")
            sys.exit(1)
        generated = gguf_files[0]
        # Move to final destination with our naming convention
        shutil.move(str(generated), str(output_path))

    file_size = output_path.stat().st_size / (1024 * 1024 * 1024)
    _write_status(npc_key, state="running", substep=f"export_{quantization}", artifact=str(output_path), artifact_size_gb=round(file_size, 4))
    print(f"  → {output_path} ({file_size:.2f} GB)")



def _file_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
    subjects_dir = PROJECT_ROOT / "subjects"
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

    # Try to get training provenance from latest run's run_manifest.json (preferred)
    # Fall back to legacy metrics.json
    try:
        latest = paths.latest_run_dir(npc_key)
        if latest:
            # Prefer run_manifest.json (richer)
            rm_path = latest / "run_manifest.json"
            if rm_path.exists():
                with open(rm_path) as f:
                    rm = json.load(f)
                manifest["provenance"] = {
                    "run_id": rm.get("run_id"),
                    "git_commit": rm.get("git_commit"),
                    "preset": rm.get("preset"),
                    "dataset_technique": rm.get("dataset", {}).get("technique"),
                    "dataset_sha256": rm.get("dataset", {}).get("train_sha256"),
                    "training_loss": rm.get("results", {}).get("training_loss"),
                    "duration_minutes": rm.get("results", {}).get("duration_minutes"),
                    "trained_at": rm.get("created_at"),
                }
                manifest["run_id"] = rm.get("run_id")
                train_loss = rm.get("results", {}).get("training_loss")
                if train_loss is not None:
                    manifest["training_loss"] = round(train_loss, 4)
                    manifest["eval_perplexity"] = round(math.exp(train_loss) if train_loss > 0 else 999, 2)
            else:
                # Fallback to legacy metrics.json
                metrics_path = latest / "metrics.json"
                if metrics_path.exists():
                    with open(metrics_path) as f:
                        metrics = json.load(f)
                    manifest["run_id"] = metrics.get("run_id")
                    manifest["trained_at"] = metrics.get("timestamp")
                    train_loss = metrics.get("training_loss")
                    if train_loss is not None:
                        manifest["training_loss"] = round(train_loss, 4)
                        manifest["eval_perplexity"] = round(math.exp(train_loss) if train_loss > 0 else 999, 2)
    except Exception:
        pass

    # Compute checksums for each GGUF file
    manifest["checksums"] = {}
    for gf in gguf_files:
        if gf.exists():
            manifest["checksums"][gf.name] = f"sha256:{_file_sha256(gf)}"

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
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume mode: skip GGUF variants that already exist",
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=5400,
        help="Per-variant export timeout in seconds (default: 5400)",
    )
    args = parser.parse_args()

    # ── Determine adapter directory ─────────────────────────────────────────
    try:
        if args.output_dir:
            npc_key, output_dir = paths.resolve_adapter_dir(args.output_dir)
        else:
            npc_key, output_dir = paths.resolve_adapter_dir(args.npc_key_or_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

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

    _write_status(
        npc_key,
        state="running",
        substep="initializing",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        model_id=model_id,
        quantization=args.quantization,
        resume=bool(args.resume),
        pid=os.getpid(),
        timeout_seconds=args.timeout_seconds,
    )

    quant_path_pre = paths.export_gguf_path(npc_key, model_id, args.quantization)
    f16_path_pre = paths.export_gguf_path(npc_key, model_id, "f16")
    if args.resume and quant_path_pre.exists() and (args.skip_f16 or f16_path_pre.exists()):
        print("[resume] Requested artifacts already exist. Regenerating manifest/checksums only.")
        gguf_files = [quant_path_pre]
        quantizations = [args.quantization]
        if not args.skip_f16:
            gguf_files.append(f16_path_pre)
            quantizations.append("f16")
        write_manifest(npc_key, model_id, quantizations, gguf_files, output_dir)
        _write_status(
            npc_key,
            state="completed",
            substep="resume_noop",
            artifacts=[str(p) for p in gguf_files],
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        print("Export resume complete (no-op).")
        return

    try:
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
        if args.resume and gguf_path.exists():
            print(f"  [resume] Skipping existing quantized GGUF: {gguf_path}")
            _write_status(npc_key, state="running", substep=f"skip_{args.quantization}", artifact=str(gguf_path))
        else:
            _export_gguf_file(
                model,
                tokenizer,
                model_id,
                args.quantization,
                gguf_path,
                npc_key=npc_key,
                substep_timeout=args.timeout_seconds,
            )

        # ── Also export f16 GGUF for deployment use ─────────────────────────────
        f16_path = paths.export_gguf_path(npc_key, model_id, "f16")
        if not args.skip_f16:
            if args.resume and f16_path.exists():
                print(f"  [resume] Skipping existing f16 GGUF: {f16_path}")
                _write_status(npc_key, state="running", substep="skip_f16", artifact=str(f16_path))
            else:
                _export_gguf_file(
                    model,
                    tokenizer,
                    model_id,
                    "f16",
                    f16_path,
                    npc_key=npc_key,
                    substep_timeout=args.timeout_seconds,
                )

        # ── Write manifest.json ────────────────────────────────────────────────
        gguf_files = [gguf_path]
        quantizations = [args.quantization]
        if not args.skip_f16:
            gguf_files.append(f16_path)
            quantizations.append("f16")
        write_manifest(npc_key, model_id, quantizations, gguf_files, output_dir)
        _write_status(npc_key, state="completed", substep="finalized", artifacts=[str(p) for p in gguf_files], completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        print(f"\nExport complete!")
        print(f"  GGUF (quant): {gguf_path}")
        if not args.skip_f16:
            print(f"  GGUF (f16):   {f16_path}")
    except Exception as exc:
        _write_status(npc_key, state="failed", substep="failed", error_summary=str(exc), failed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        raise


if __name__ == "__main__":
    main()
