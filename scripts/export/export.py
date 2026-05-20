#!/usr/bin/env python3
"""
export.py — GGUF Model Exporter & Quantizer

This script exports trained LoRA adapters to GGUF format for Unity/LLMUnity.

Two modes:
  1. Adapter mode (default, for Unity): Produces a small LoRA-only GGUF via
     llama.cpp's convert_lora_to_gguf.py. Fast, no base model loading.
  2. Full-merge mode (--full-merge): Merges LoRA into base model and exports
     as a standalone GGUF. Uses single f16 export + llama-quantize for
     additional quant levels (avoids redundant unsloth passes).

Usage:
    # Adapter mode (default, recommended for Unity NPCs):
    ./ucore export chemistry_instructor

    # Full-merge mode:
    ./ucore export chemistry_instructor --full-merge --quantization q4_k_m
"""

import argparse
import contextlib
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from scripts.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path

# ── llama.cpp toolchain paths ─────────────────────────────────────────────
LLAMA_CPP_DIR = Path.home() / ".unsloth" / "llama.cpp"
CONVERTER = LLAMA_CPP_DIR / "convert_lora_to_gguf.py"
LLAMA_QUANTIZE = LLAMA_CPP_DIR / "build" / "bin" / "llama-quantize"

CONVERTER_CANDIDATES = [
    CONVERTER,
    LLAMA_CPP_DIR / "convert" / "convert_lora_to_gguf.py",
    PROJECT_ROOT / "scripts" / "convert_lora_to_gguf.py",
    Path.home() / "llama.cpp" / "convert_lora_to_gguf.py",
    Path("/usr/local/lib/llama.cpp/convert_lora_to_gguf.py"),
]
CONVERTER_GITHUB_URL = (
    "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_lora_to_gguf.py"
)


def _find_converter() -> Path | None:
    """Find convert_lora_to_gguf.py in standard locations."""
    for candidate in CONVERTER_CANDIDATES:
        if candidate.exists():
            return candidate
    import shutil
    found = shutil.which("convert_lora_to_gguf.py")
    if found:
        return Path(found)
    return None


def _download_converter(target_dir: Path | None = None) -> Path | None:
    """Download the converter script from GitHub as last resort."""
    if target_dir is None:
        target_dir = PROJECT_ROOT
    target = target_dir / "convert_lora_to_gguf.py"
    if target.exists():
        return target
    print(f"  [export] Converter not found locally. Downloading from GitHub...")
    try:
        import urllib.request
        urllib.request.urlretrieve(CONVERTER_GITHUB_URL, str(target))
        print(f"  [export] Downloaded to {target}")
        return target
    except Exception as e:
        print(f"  [export] Failed to download converter: {e}")
        return None


def _validate_tokenizer(tokenizer, model_id: str, npc_key: str) -> None:
    """Validate tokenizer configuration before export.

    Checks chat_template presence and EOS token configuration.
    Warns about common misconfigurations that cause gibberish output.
    """
    if not hasattr(tokenizer, "chat_template") or not tokenizer.chat_template:
        print(f"  [WARN] Tokenizer has no chat_template set.")
        print(f"  Without a chat template, the model may produce gibberish in Unity.")
        print(f"  Set tokenizer.chat_template before export or verify in the base model.")
    else:
        print(f"  [OK]   Chat template: {repr(tokenizer.chat_template[:60])}...")

    eos = tokenizer.eos_token
    eos_id = tokenizer.eos_token_id
    pad = tokenizer.pad_token
    if not eos:
        print(f"  [WARN] No EOS token set. Inference may produce infinite generation.")
    else:
        print(f"  [OK]   EOS token: {repr(eos)} (id={eos_id})")
    if not pad:
        print(f"  [NOTE] No pad token set — setting to EOS for export.")
        tokenizer.pad_token = eos
        tokenizer.pad_token_id = eos_id


def _get_clean_config(adapter_path) -> str | None:
    """Get clean config.json from adapter's base model (strips bitsandbytes keys).

    Returns path to a temp directory containing the cleaned config.json.
    Caller must clean up the returned directory.
    """
    adapter_config_path = Path(adapter_path) / "adapter_config.json"
    if not adapter_config_path.exists():
        print(f"Error: {adapter_config_path} not found")
        return None

    with open(adapter_config_path) as f:
        adapter_config = json.load(f)

    base_model = adapter_config.get("base_model_name_or_path")
    if not base_model:
        print("Error: No base_model_name_or_path in adapter_config.json")
        return None

    print(f"  Adapter base model: {base_model}")

    # Try cached config first
    configs_dir = PROJECT_ROOT / "configs" / "base_configs"
    if configs_dir.exists():
        cached_name = base_model.replace("/", "-").replace("_", "-")
        cached_path = configs_dir / f"{cached_name}.json"
        if cached_path.exists():
            print(f"  Using cached config: {cached_path}")
            with open(cached_path) as f:
                config = json.load(f)
            tmp_dir = tempfile.mkdtemp(prefix="lora-gguf-config-")
            with open(os.path.join(tmp_dir, "config.json"), "w") as f:
                json.dump(config, f)
            return tmp_dir

    # Try HuggingFace
    try:
        from huggingface_hub import hf_hub_download
        token_path = Path.home() / ".cache" / "huggingface" / "token"
        token = token_path.read_text().strip() if token_path.exists() else None
        config_path = hf_hub_download(base_model, "config.json", token=token)
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        print(f"  Could not load config from HF: {e}")
        from transformers import AutoConfig
        try:
            config = AutoConfig.from_pretrained(base_model).to_dict()
        except Exception as e2:
            print(f"  Could not load config locally either: {e2}")
            print("  Provide a clean config dir with --base-config")
            return None

    # Strip bitsandbytes keys
    for key in ["quantization_config", "quant_method"]:
        config.pop(key, None)

    tmp_dir = tempfile.mkdtemp(prefix="lora-gguf-config-")
    with open(os.path.join(tmp_dir, "config.json"), "w") as f:
        json.dump(config, f)
    return tmp_dir


def _export_adapter_gguf(adapter_path: Path, npc_key: str, outtype: str = "f16",
                         output_path: Path | None = None) -> Path:
    """Export LoRA adapter as a lightweight GGUF using convert_lora_to_gguf.py.

    No base model loading needed — just the adapter weights + config.
    Fast output suitable for Unity/LLMUnity LoRA loading.
    """
    converter = _find_converter()
    if converter is None:
        converter = _download_converter()
    if converter is None:
        print("Error: convert_lora_to_gguf.py not found.")
        print("  Install llama.cpp or download from:")
        print(f"  {CONVERTER_GITHUB_URL}")
        sys.exit(1)

    if output_path is None:
        # Adapter GGUFs go in exports/{npc_key}/{npc_key}-lora-{outtype}.gguf
        base_name = f"{npc_key}-lora-{outtype}.gguf"
        output_path = paths.export_dir(npc_key) / base_name
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    clean_config_dir = _get_clean_config(adapter_path)
    if clean_config_dir is None:
        sys.exit(1)

    try:
        cmd = [
            sys.executable, str(converter),
            str(adapter_path),
            "--outtype", outtype,
            "--outfile", str(output_path),
            "--base", clean_config_dir,
        ]
        print(f"  Running: convert_lora_to_gguf.py --outtype {outtype}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        for line in result.stdout.splitlines():
            print(f"    {line}")
        if result.returncode != 0:
            for line in result.stderr.splitlines():
                print(f"    ERR: {line}")
            print(f"  Conversion failed (exit {result.returncode})")
            sys.exit(result.returncode)

        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"  Adapter GGUF: {output_path} ({size_mb:.1f} MB)")
        return output_path
    finally:
        if os.path.exists(clean_config_dir):
            shutil.rmtree(clean_config_dir, ignore_errors=True)


def _quantize_gguf(f16_path: Path, output_path: Path, quant_type: str) -> Path:
    """Quantize an f16 GGUF to a lower bit width using llama-quantize."""
    if not LLAMA_QUANTIZE.exists():
        print(f"Warning: llama-quantize not found at {LLAMA_QUANTIZE}")
        print("  Install the complete ~/.unsloth/llama.cpp build with CUDA support.")
        return None

    cmd = [str(LLAMA_QUANTIZE), str(f16_path), str(output_path), quant_type]
    print(f"  Quantizing: {quant_type} via llama-quantize...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    for line in result.stdout.splitlines():
        print(f"    {line}")

    if result.returncode != 0:
        for line in result.stderr.splitlines():
            print(f"    ERR: {line}")
        print(f"  Quantization failed (exit {result.returncode})")
        return None

    if output_path.exists():
        size_gb = output_path.stat().st_size / (1024**3)
        print(f"  → {output_path} ({size_gb:.2f} GB)")
    return output_path


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


def _export_gguf_file(model, tokenizer, model_id, quantization, output_path, *, npc_key: str, substep_timeout: int | None = None, maximum_memory: float | None = None):
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
                    maximum_memory_usage=maximum_memory,
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
    spec_path = paths.spec_path(npc_key)
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
        help="GGUF quantization method for full-merge mode (default: q4_k_m)",
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
        "--full-merge", action="store_true",
        help="Produce a full merged GGUF (loads base model, slower). Default is LoRA adapter only.",
    )
    parser.add_argument(
        "--skip-f16", action="store_true",
        help="In full-merge mode: skip exporting the f16 variant (quantize directly from adapter)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume mode: skip GGUFs that already exist",
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=5400,
        help="Per-variant export timeout in seconds (default: 5400)",
    )
    parser.add_argument(
        "--maximum-memory", type=float, default=None,
        help="Maximum memory (GB) for save_pretrained_gguf. Reduces OOM risk on large models.",
    )
    parser.add_argument(
        "--outtype", default="f16",
        choices=["f32", "f16", "bf16", "q8_0"],
        help="LoRA adapter output format (default: f16). Only used in adapter mode.",
    )
    parser.add_argument(
        "--workflow-hooks", default=None,
        help="Path to a JSONL hook log for step tracing (default: <export-dir>/workflow_hooks.jsonl)",
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

    _write_status(
        npc_key,
        state="running",
        substep="initializing",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        mode="full_merge" if args.full_merge else "adapter",
        quantization=args.quantization,
        resume=bool(args.resume),
        pid=os.getpid(),
        timeout_seconds=args.timeout_seconds,
    )
    hook_recorder = WorkflowHookRecorder(args.workflow_hooks or default_hook_path(paths.export_dir(npc_key)), tool="export", npc_key=npc_key)
    hook_recorder.emit("export_pipeline", "start", mode="full_merge" if args.full_merge else "adapter", quantization=args.quantization, resume=bool(args.resume), output_dir=str(output_dir))

    if not args.full_merge:
        # ── Adapter mode (default) — fast, no base model loading ─────────────
        print(f"Mode: adapter-only (for Unity/LLMUnity)")
        print(f"  Adapter: {output_dir}")
        print(f"  NPC:     {npc_key}")
        print(f"  Outtype: {args.outtype}")

        hook_recorder.emit("export_adapter", "start", outtype=args.outtype, output_dir=str(output_dir))
        output_path = _export_adapter_gguf(
            output_dir, npc_key,
            outtype=args.outtype,
        )
        hook_recorder.emit("export_adapter", "complete", outtype=args.outtype, output_path=str(output_path))

        # Write manifest
        write_manifest(
            npc_key, "adapter",
            [f"lora-{args.outtype}"],
            [output_path], output_dir,
        )
        _write_status(
            npc_key, state="completed", substep="adapter_done",
            artifacts=[str(output_path)],
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        hook_recorder.emit("export_pipeline", "complete", mode="adapter", artifacts=[str(output_path)])
        print(f"\nExport complete! Adapter GGUF ready for Unity.")
        print(f"  Load in LLMUnity: base_model.gguf + lora_adapter.gguf")
        print(f"  Size: {output_path.stat().st_size / 1e6:.1f} MB")
        return

    # ── Full-merge mode — optimized: single f16 export + local quantize ─────
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

    print(f"Mode: full-merge (standalone GGUF)")
    print(f"  Adapter:  {output_dir}")
    print(f"  NPC key:  {npc_key}")
    print(f"  Model ID: {model_id}")

    quant_path = paths.export_gguf_path(npc_key, model_id, args.quantization)
    f16_path = paths.export_gguf_path(npc_key, model_id, "f16")

    # Check resume
    if args.resume and quant_path.exists() and (args.skip_f16 or f16_path.exists()):
        print("[resume] Artifacts exist. Regenerating manifest.")
        gguf_files = [quant_path]
        quantizations = [args.quantization]
        if not args.skip_f16:
            gguf_files.append(f16_path)
            quantizations.append("f16")
        write_manifest(npc_key, model_id, quantizations, gguf_files, output_dir)
        _write_status(npc_key, state="completed", substep="resume_noop",
                      artifacts=[str(p) for p in gguf_files])
        hook_recorder.emit("export_pipeline", "complete", mode="full_merge", resume=True, artifacts=[str(p) for p in gguf_files])
        print("Export resume complete (no-op).")
        return

    try:
        hook_recorder.emit("export_full_merge", "start", model_id=model_id, quantization=args.quantization)
        # ── Load model ──────────────────────────────────────────────────────
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

        # ── Validate tokenizer configuration ────────────────────────────────
        _validate_tokenizer(tokenizer, model_id, npc_key)

        # ── Load LoRA adapter ──────────────────────────────────────────────
        adapter_path = output_dir / "adapter_config.json"
        if adapter_path.exists():
            print(f"  Loading LoRA adapter from: {output_dir}")
            model = PeftModel.from_pretrained(model, str(output_dir), is_trainable=False)
            model.save_pretrained_gguf = types.MethodType(
                unsloth_save.unsloth_save_pretrained_gguf, model,
            )

        # ── Export only f16 via unsloth (one slow pass) ─────────────────────
        f16_path = paths.export_gguf_path(npc_key, model_id, "f16")
        if args.resume and f16_path.exists():
            print(f"  [resume] Skipping f16 export — already exists")
        else:
            _export_gguf_file(
                model, tokenizer, model_id, "f16",
                f16_path,
                npc_key=npc_key,
                substep_timeout=args.timeout_seconds,
                maximum_memory=args.maximum_memory,
            )

        # ── Quantize to target format via llama-quantize (fast) ─────────────
        gguf_files = [f16_path]
        quantizations = ["f16"]

        if args.quantization and args.quantization != "f16":
            if args.resume and quant_path.exists():
                print(f"  [resume] Skipping {args.quantization} — already exists")
            else:
                result = _quantize_gguf(f16_path, quant_path, args.quantization)
                if result:
                    gguf_files.append(quant_path)
                    quantizations.append(args.quantization)
                else:
                    print(f"  [WARN] Local quantization to {args.quantization} failed.")
                    print(f"  The f16 GGUF is still available at: {f16_path}")
                    print(f"  You can run quantize manually:")
                    print(f"    {LLAMA_QUANTIZE} {f16_path} {quant_path} {args.quantization}")

        # ── Write manifest ──────────────────────────────────────────────────
        write_manifest(npc_key, model_id, quantizations, gguf_files, output_dir)
        _write_status(
            npc_key, state="completed", substep="finalized",
            artifacts=[str(p) for p in gguf_files],
            completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        hook_recorder.emit("export_full_merge", "complete", model_id=model_id, quantizations=quantizations, artifacts=[str(p) for p in gguf_files])
        hook_recorder.emit("export_pipeline", "complete", mode="full_merge", quantizations=quantizations, artifacts=[str(p) for p in gguf_files])

        print(f"\nExport complete!")
        print(f"  GGUF (f16):       {f16_path}")
        if args.quantization and args.quantization != "f16" and quant_path.exists():
            print(f"  GGUF ({args.quantization}): {quant_path}")

    except Exception as exc:
        _write_status(npc_key, state="failed", substep="failed",
                      error_summary=str(exc),
                      failed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        hook_recorder.emit("export_pipeline", "error", mode="full_merge" if args.full_merge else "adapter", error=str(exc))
        raise


if __name__ == "__main__":
    main()
