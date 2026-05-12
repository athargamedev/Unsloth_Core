#!/usr/bin/env python3
"""
export_adapter.py — Export a PEFT LoRA adapter to GGUF format for LLMUnity.

Converts the safeTensors adapter weights saved by model.save_pretrained()
into a smaller GGUF adapter file loadable at runtime by llama.cpp / LLMUnity.

Usage:
    # Single adapter
    python scripts/export_adapter.py outputs/bible_instructor

    # Batch convert all adapters in outputs/
    python scripts/export_adapter.py --all

    # Specify outtype
    python scripts/export_adapter.py outputs/marvel_instructor --outtype q8_0
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from _config import paths
CONVERTER = Path.home() / ".unsloth" / "llama.cpp" / "convert_lora_to_gguf.py"

# Locations to search for the llama.cpp converter script
CONVERTER_CANDIDATES = [
    CONVERTER,  # ~/.unsloth/llama.cpp/ (Unsloth's default install)
    Path.home() / ".unsloth" / "llama.cpp" / "convert" / "convert_lora_to_gguf.py",
    Path.home() / "llama.cpp" / "convert_lora_to_gguf.py",
    Path("/usr/local/lib/llama.cpp/convert_lora_to_gguf.py"),
]

CONVERTER_GITHUB_URL = (
    "https://raw.githubusercontent.com/ggml-org/llama.cpp/master/convert_lora_to_gguf.py"
)


def _find_converter() -> Path | None:
    """Find the convert_lora_to_gguf.py script by searching standard locations."""
    for candidate in CONVERTER_CANDIDATES:
        if candidate.exists():
            return candidate
    # Try PATH lookup
    import shutil
    found = shutil.which("convert_lora_to_gguf.py")
    if found:
        return Path(found)
    return None


def _download_converter(target_dir: Path | None = None) -> Path | None:
    """Download the converter script from GitHub as a last resort.
    
    Returns path to the downloaded script, or None if download fails.
    """
    if target_dir is None:
        target_dir = PROJECT_ROOT
    target = target_dir / "convert_lora_to_gguf.py"
    if target.exists():
        return target
    print(f"[export] Converter not found locally. Downloading from GitHub...")
    try:
        import urllib.request
        urllib.request.urlretrieve(CONVERTER_GITHUB_URL, str(target))
        print(f"[export] Downloaded to {target}")
        return target
    except Exception as e:
        print(f"[export] Failed to download converter: {e}")
        return None

# Known base models and their quantization config keys to strip
BASE_MODEL_CONFIGS = {}  # populated on demand


def _get_clean_config(adapter_path):
    """Get a clean config.json by stripping bitsandbytes keys from the adapter's base model config.

    Returns path to a temp directory containing the cleaned config.json.
    The caller is responsible for cleanup.
    """
    adapter_config_path = Path(adapter_path) / "adapter_config.json"
    if not adapter_config_path.exists():
        print(f"Error: {adapter_config_path} not found")
        sys.exit(1)

    with open(adapter_config_path) as f:
        adapter_config = json.load(f)

    base_model = adapter_config.get("base_model_name_or_path")
    if not base_model:
        print(f"Error: No base_model_name_or_path in adapter_config.json")
        sys.exit(1)

    print(f"[export] Base model: {base_model}")

    # Try cached config first
    configs_dir = Path(__file__).resolve().parent.parent / "configs" / "base_configs"
    if configs_dir.exists():
        # Match by pattern: e.g. "unsloth/Llama-3.2-3B-Instruct-bnb-4bit" -> "unsloth-Llama-3.2-3B-Instruct-bnb-4bit.json"
        cached_name = base_model.replace("/", "-").replace("_", "-")
        cached_path = configs_dir / f"{cached_name}.json"
        if cached_path.exists():
            print(f"[export] Using cached config: {cached_path}")
            with open(cached_path) as f:
                config = json.load(f)
            tmp_dir = tempfile.mkdtemp(prefix="lora-gguf-config-")
            with open(os.path.join(tmp_dir, "config.json"), "w") as f:
                json.dump(config, f)
            return tmp_dir

    # Try to get config from HuggingFace cache first
    try:
        from huggingface_hub import hf_hub_download
        token_path = Path.home() / ".cache" / "huggingface" / "token"
        token = token_path.read_text().strip() if token_path.exists() else None

        config_path = hf_hub_download(base_model, "config.json", token=token)
        with open(config_path) as f:
            config = json.load(f)
    except Exception as e:
        print(f"[export] Could not load config from HF: {e}")
        # Fallback: check if the base model is cached locally
        from transformers import AutoConfig
        try:
            config = AutoConfig.from_pretrained(base_model).to_dict()
        except Exception as e2:
            print(f"[export] Could not load config locally either: {e2}")
            print(f"[export] You may need to manually provide a base config.")
            print(f"[export] Try: --base /path/to/clean/config/dir")
            sys.exit(1)

    # Strip quantization keys that bitsandbytes models have
    for key in ["quantization_config", "quant_method"]:
        config.pop(key, None)

    # Create temp dir with just the config
    tmp_dir = tempfile.mkdtemp(prefix="lora-gguf-config-")
    with open(os.path.join(tmp_dir, "config.json"), "w") as f:
        json.dump(config, f)

    return tmp_dir


def convert_adapter(adapter_path, outtype="f16", output_path=None, clean_config_dir=None):
    """Convert a PEFT adapter directory to a GGUF-format LoRA adapter.

    Args:
        adapter_path: Path to directory containing adapter_model.safetensors + adapter_config.json
        outtype: Output format (f32, f16, bf16, q8_0, auto). Default: f16
        output_path: Explicit output path. If None, auto-generated.
        clean_config_dir: Path to dir with clean config.json. If None, auto-generated.

    Returns:
        Path to the output GGUF file.
    """
    try:
        npc_key, adapter_path = paths.resolve_adapter_dir(adapter_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    # Sanity check
    if not (adapter_path / "adapter_config.json").exists():
        print(f"Error: {adapter_path} does not contain adapter_config.json")
        print(f"       Is this a PEFT LoRA adapter directory?")
        sys.exit(1)

    # Determine output path
    if output_path is None:
        output_path = str(adapter_path / f"{npc_key}-lora.{outtype}.gguf")
    else:
        output_path = str(Path(output_path))

    print(f"[export] Converting adapter: {adapter_path}")
    print(f"[export] Output: {output_path}")
    print(f"[export] Outtype: {outtype}")

    # Get clean config
    owned_tmpdir = None
    if clean_config_dir is None:
        owned_tmpdir = _get_clean_config(adapter_path)
        clean_config_dir = owned_tmpdir

    try:
        converter = _find_converter()
        if converter is None:
            converter = _download_converter()
        if converter is None:
            print("[export] Converter not available. Cannot convert adapter to GGUF.")
            print(f"[export] Install llama.cpp or manually run:")
            print(f"[export]   python convert_lora_to_gguf.py {adapter_path} "
                  f"--outtype {outtype} --outfile {output_path} --base <clean-config-dir>")
            sys.exit(1)

        cmd = [
            sys.executable,
            str(converter),
            str(adapter_path),
            "--outtype", outtype,
            "--outfile", output_path,
            "--base", clean_config_dir,
        ]

        print(f"[export] Running: {' '.join(str(c) for c in cmd)}")
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)

        # Always print output
        for line in result.stdout.splitlines():
            print(f"  {line}")

        if result.returncode != 0:
            for line in result.stderr.splitlines():
                print(f"  ERR: {line}")
            print(f"[export] Conversion failed with exit code {result.returncode}")
            sys.exit(result.returncode)

        # Verify output
        output_file = Path(output_path)
        if output_file.exists():
            size_mb = output_file.stat().st_size / (1024 * 1024)
            print(f"[export] Done! {output_path} ({size_mb:.1f} MB)")
        else:
            print(f"[export] Warning: Output file not found at expected path")
            print(f"[export] Converter said: {result.stdout.strip().splitlines()[-1] if result.stdout.strip() else '?'}")

        return str(output_file)

    finally:
        # Clean up temp dir
        if owned_tmpdir and os.path.exists(owned_tmpdir):
            shutil.rmtree(owned_tmpdir, ignore_errors=True)


def find_all_adapters():
    """Find all PEFT adapter directories under outputs/."""
    outputs_dir = PROJECT_ROOT / "outputs"
    if not outputs_dir.exists():
        print(f"Error: {outputs_dir} does not exist")
        return []

    adapters = []
    for entry in sorted(outputs_dir.iterdir()):
        if not entry.is_dir() or entry.name == "colab":
            continue
        try:
            _, adapter_dir = paths.resolve_adapter_dir(str(entry))
            adapters.append(str(adapter_dir))
        except FileNotFoundError:
            continue
    return adapters


def main():
    parser = argparse.ArgumentParser(description="Export PEFT LoRA adapter to GGUF format")
    parser.add_argument("adapter_path", nargs="?",
                        help="Path to PEFT adapter directory (containing adapter_model.safetensors)")
    parser.add_argument("--all", "-a", action="store_true",
                        help="Convert all adapters in outputs/")
    parser.add_argument("--outtype", default="f16",
                        choices=["f32", "f16", "bf16", "q8_0", "auto"],
                        help="Output format (default: f16)")
    parser.add_argument("--outfile", help="Explicit output path")
    parser.add_argument("--base", help="Path to directory containing clean config.json "
                                        "(auto-generated from base model config if not provided)")

    args = parser.parse_args()

    converter = _find_converter()
    if converter is None:
        print("Warning: convert_lora_to_gguf.py not found locally.")
        converter = _download_converter()
    if converter is None:
        print("Error: Converter not found. Install llama.cpp or check the path.")
        print("  Expected locations searched:")
        for c in CONVERTER_CANDIDATES:
            print(f"    - {c}")
        print(f"  Also checked PATH, and attempted download from:")
        print(f"    {CONVERTER_GITHUB_URL}")
        sys.exit(1)

    if args.all:
        adapters = find_all_adapters()
        if not adapters:
            print("No adapter directories found in outputs/")
            sys.exit(1)
        print(f"[export] Found {len(adapters)} adapters to convert:\n")
        for ad in adapters:
            print(f"  - {ad}")
        print()
        for ad in adapters:
            convert_adapter(str(ad), outtype=args.outtype, clean_config_dir=args.base)
        print(f"\n[export] All {len(adapters)} adapters converted.")
    elif args.adapter_path:
        convert_adapter(args.adapter_path, outtype=args.outtype,
                        output_path=args.outfile, clean_config_dir=args.base)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
