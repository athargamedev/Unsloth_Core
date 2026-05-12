#!/usr/bin/env python3
"""
train.py — Unified Unsloth training launcher with model-size-aware presets.

Usage:
    # Train from a YAML config
    python scripts/train.py configs/lora-sft-fast-3b.yaml

    # Direct CLI mode (uses base config + presets)
    python scripts/train.py --model unsloth/Qwen3-1.7B-bnb-4bit \
        --preset fast-1.7b \
        --data datasets/chemistry_instructor/notebooklm/train.jsonl \
        --output outputs/chemistry_instructor

    # With a custom YAML and overrides
    python scripts/train.py configs/lora-sft-quality-1.7b.yaml \
        --data datasets/chemistry_instructor/notebooklm/train.jsonl \
        --conv-ext 3 \
        --mix-general 0.15

    # Full pipeline: auto-generate dataset from spec, then train
    python scripts/train.py subjects/chemistry_instructor.json --from-spec

    # Post-training export (with already-trained model in output dir)
    python scripts/train.py configs/lora-sft-fast-3b.yaml --export-gguf

    # Export only the LoRA adapter as GGUF (for LLMUnity runtime loading)
    python scripts/train.py configs/lora-sft-fast-3b.yaml --export-lora

    # One-liner: generate dataset from spec, train with preset, export LoRA
    python scripts/train.py subjects/chemistry_instructor.json --from-spec --preset fast-1.7b --export-lora
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths

# ── Model-size-aware presets ────────────────────────────────────────────────
# Each preset overrides the base YAML config for specific model sizes.
# Effective batch size = batch_size * gradient_accumulation_steps.
# Target: 16 for stable convergence (per QLoRA paper), adjusted for 6GB VRAM.
# Presets are loaded from configs/presets/ as override-only YAML files.
PRESETS_DIR = PROJECT_ROOT / "configs" / "presets"


def deep_merge(base, override):
    """Deep merge two dicts. override values take precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_preset(preset_name):
    """Load a preset YAML file from configs/presets/."""
    preset_path = PRESETS_DIR / f"{preset_name}.yaml"
    if not preset_path.exists():
        print(f"Error: Unknown preset '{preset_name}'")
        available = get_available_presets()
        print(f"Available presets: {', '.join(available)}")
        sys.exit(1)
    with open(preset_path) as f:
        return yaml.safe_load(f)


def get_available_presets():
    """List available presets from the presets directory."""
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.name.replace(".yaml", "") for p in PRESETS_DIR.glob("*.yaml"))


def get_preset_description(preset_name):
    """Get the first comment/description from a preset YAML."""
    preset_path = PRESETS_DIR / f"{preset_name}.yaml"
    if preset_path.exists():
        with open(preset_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("#"):
                    return line.lstrip("# ").strip()
    return ""


def load_config(config_path, preset=None, overrides=None):
    """Load a YAML config, apply preset overrides, then CLI overrides."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Apply preset overrides from YAML file
    if preset:
        preset_config = load_preset(preset)
        config = deep_merge(config, preset_config)

    # Apply CLI overrides
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                if key in ("model",):
                    config[key] = value
                elif key in ("batch_size", "gradient_accumulation_steps", "num_epochs",
                             "max_steps", "learning_rate", "weight_decay", "warmup_steps",
                             "save_steps", "eval_steps", "max_seq_length", "packing",
                             "train_on_responses_only"):
                    config.setdefault("training", {})[key] = value
                elif key in ("lora_r", "lora_alpha", "lora_dropout"):
                    config.setdefault("lora", {})[key] = value
                elif key in ("output_dir",):
                    config.setdefault("training", {})["output_dir"] = value

    # Fill defaults
    training = config.setdefault("training", {})
    training.setdefault("num_epochs", 3)
    training.setdefault("learning_rate", 2e-4)
    training.setdefault("batch_size", 1)
    training.setdefault("gradient_accumulation_steps", 8)
    training.setdefault("warmup_steps", 10)
    training.setdefault("save_steps", 50)
    training.setdefault("eval_steps", 50)
    training.setdefault("weight_decay", 0.01)
    training.setdefault("max_seq_length", 2048)
    training.setdefault("packing", True)
    training.setdefault("train_on_responses_only", True)
    training.setdefault("output_dir", str(PROJECT_ROOT / "outputs" / "default"))
    training.setdefault("max_steps", -1)

    lora = config.setdefault("lora", {})
    lora.setdefault("lora_r", 16)
    lora.setdefault("lora_alpha", 32)
    lora.setdefault("lora_dropout", 0.0)
    lora.setdefault("target_modules",
                     "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj")

    config.setdefault("logging", {})
    config["logging"].setdefault("enable_tensorboard", True)

    # Resolve relative output_dir against PROJECT_ROOT
    output_dir = training.get("output_dir", "")
    if output_dir and not Path(output_dir).is_absolute():
        training["output_dir"] = str(PROJECT_ROOT / output_dir)

    return config


def print_config(config, preset_name=None):
    """Pretty-print the resolved training configuration."""
    print("=" * 60)
    print("  TRAINING CONFIGURATION")
    if preset_name:
        desc = get_preset_description(preset_name)
        print(f"  Preset: {preset_name} — {desc}")
    print("=" * 60)
    print(f"  Model:       {config.get('model', '(not set)')}")
    training = config.get("training", {})
    print(f"  Output:      {training.get('output_dir', '(not set)')}")
    print(f"  Max seq len: {training.get('max_seq_length', 2048)}")
    print(f"  Batch size:  {training.get('batch_size', 1)}")
    print(f"  Grad accum:  {training.get('gradient_accumulation_steps', 8)}")
    eff = training.get("batch_size", 1) * training.get("gradient_accumulation_steps", 8)
    print(f"  Eff. batch:  {eff}")
    print(f"  Epochs:      {training.get('num_epochs', 3)}")
    if training.get("max_steps", -1) > 0:
        print(f"  Max steps:   {training['max_steps']}")
    print(f"  LR:          {training.get('learning_rate', 2e-4)}")
    print(f"  Packing:     {training.get('packing', True)}")
    print(f"  Train resp:  {training.get('train_on_responses_only', True)}")
    lora = config.get("lora", {})
    print(f"  LoRA r:      {lora.get('lora_r', 16)}")
    print(f"  LoRA alpha:  {lora.get('lora_alpha', 32)}")
    print(f"  LoRA drop:   {lora.get('lora_dropout', 0.0)}")
    print(f"  Targets:     {lora.get('target_modules', 'all')}")
    print("=" * 60)


def prepare_dataset(data_path, tokenizer, config):
    """Load and prepare the dataset with packing, chat template."""
    from datasets import Dataset, load_dataset
    from unsloth.chat_templates import get_chat_template

    training = config.get("training", {})

    print(f"\n[dataset] Loading: {data_path}")

    # Load JSONL
    if data_path.endswith(".jsonl"):
        dataset = load_dataset("json", data_files=data_path, split="train")
    elif data_path.endswith(".json"):
        dataset = load_dataset("json", data_files=data_path, split="train")
    else:
        dataset = load_dataset(data_path, split="train")

    print(f"[dataset] Loaded {len(dataset)} examples")

    # Apply chat template to tokenizer (Unsloth 2026.5.2: get_chat_template modifies tokenizer, not dataset)
    print("[dataset] Applying chatml template to tokenizer")
    tokenizer = get_chat_template(
        tokenizer,
        chat_template="chatml",
    )

    # Convert messages column to 'text' via tokenizer's chat_template (standard Unsloth pattern)
    def _format_chat(example):
        example["text"] = tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False,
        )
        return example

    print(f"[dataset] Converting messages to text via apply_chat_template")
    dataset = dataset.map(_format_chat)
    print(f"[dataset] Text sample: {dataset[0]['text'][:120]}...")

    # Check for validation split
    val_path = str(paths.infer_validation_path(data_path))
    eval_dataset = None
    if val_path and os.path.exists(val_path):
        print(f"[dataset] Found validation set: {val_path}")
        eval_dataset = load_dataset("json", data_files=val_path, split="train")
        eval_dataset = eval_dataset.map(_format_chat)

    return dataset, eval_dataset, tokenizer


def setup_model_and_tokenizer(config):
    """Load the base model and tokenizer with 4-bit quantization via Unsloth."""
    from unsloth import FastLanguageModel

    training = config.get("training", {})
    lora = config.get("lora", {})

    model_name = config.get("model", "unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
    max_seq_length = training.get("max_seq_length", 2048)
    load_in_4bit = training.get("load_in_4bit", True)

    print(f"\n[model] Loading: {model_name}")
    print(f"[model] Max seq len: {max_seq_length}")
    print(f"[model] 4-bit: {load_in_4bit}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,  # Auto-detect
        load_in_4bit=load_in_4bit,
    )

    # Configure LoRA
    print(f"[model] Adding LoRA: r={lora['lora_r']}, alpha={lora['lora_alpha']}")
    target_modules = [m.strip() for m in lora.get("target_modules", "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj").split(",")]
    model = FastLanguageModel.get_peft_model(
        model,
        r=lora.get("lora_r", 16),
        lora_alpha=lora.get("lora_alpha", 32),
        lora_dropout=lora.get("lora_dropout", 0.0),
        target_modules=target_modules,
        use_gradient_checkpointing="unsloth",
        random_state=42,
        max_seq_length=max_seq_length,
    )

    return model, tokenizer


def run_training(model, tokenizer, dataset, eval_dataset, config):
    """Run the SFT training loop."""
    from trl import SFTTrainer
    from transformers import TrainingArguments
    import torch

    training = config.get("training", {})
    output_dir = training.get("output_dir", str(PROJECT_ROOT / "outputs" / "default"))
    os.makedirs(output_dir, exist_ok=True)

    effective_batch = training.get("batch_size", 1) * training.get("gradient_accumulation_steps", 8)
    print(f"\n[train] Effective batch size: {effective_batch}")

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=training.get("num_epochs", 3),
        max_steps=training.get("max_steps", -1) if training.get("max_steps", -1) > 0 else -1,
        per_device_train_batch_size=training.get("batch_size", 1),
        gradient_accumulation_steps=training.get("gradient_accumulation_steps", 8),
        warmup_steps=training.get("warmup_steps", 10),
        learning_rate=training.get("learning_rate", 2e-4),
        weight_decay=training.get("weight_decay", 0.01),
        neftune_noise_alpha=training.get("neftune_noise_alpha", None),
        logging_steps=1,
        save_steps=training.get("save_steps", 50),
        eval_steps=training.get("eval_steps", 50),
        eval_strategy="steps" if eval_dataset else "no",
        save_total_limit=3,
        load_best_model_at_end=True if eval_dataset else False,
        report_to="tensorboard" if config.get("logging", {}).get("enable_tensorboard", True) else "none",
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        optim="adamw_8bit",
        seed=42,
        data_seed=42,
        ddp_find_unused_parameters=False if torch.cuda.device_count() > 1 else None,
        remove_unused_columns=False,
        dataloader_pin_memory=False,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=training.get("max_seq_length", 2048),
        dataset_num_proc=2,
        packing=training.get("packing", True),
        args=args,
    )

    # Apply train_on_responses_only to mask user tokens in loss (Unsloth 2026.5.2 API)
    if training.get("train_on_responses_only", True):
        from unsloth.chat_templates import train_on_responses_only as apply_toro
        print("[train] Applying train_on_responses_only")
        trainer = apply_toro(
            trainer,
            instruction_part="<|im_start|>user\n",
            response_part="<|im_start|>assistant\n",
            tokenizer=tokenizer,
        )

    print(f"\n[train] Starting training (output: {output_dir})")
    print(f"[train] {'=' * 50}")
    trainer_stats = trainer.train()

    print(f"\n[train] Training complete!")
    print(f"[train] Final loss: {trainer_stats.training_loss:.4f}")

    # Save the fine-tuned LoRA adapter
    print(f"\n[train] Saving LoRA adapter to {output_dir}")
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    return output_dir, trainer_stats


def export_to_gguf(model, tokenizer, output_dir, quantization="q4_k_m"):
    """Export the fine-tuned model to GGUF format using conventions from _config/paths.
    
    Uses a temp directory because save_pretrained_gguf writes to a directory,
    not a single file. The generated .gguf is then moved to the final path.
    """
    import json

    # Resolve run output dirs back to their owning NPC key.
    try:
        npc_key, adapter_dir = paths.resolve_adapter_dir(output_dir)
    except FileNotFoundError:
        adapter_dir = Path(output_dir)
        npc_key = adapter_dir.parent.parent.name if adapter_dir.parent.name == "runs" else adapter_dir.name
    # Model ID — try to read from adapter_config, fall back to default
    model_id = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
    adapter_config = adapter_dir / "adapter_config.json"
    if adapter_config.exists():
        try:
            with open(adapter_config) as f:
                cfg = json.load(f)
            model_id = cfg.get("base_model_name_or_path", model_id)
        except Exception:
            pass

    def _do_export(quant):
        """Internal: save to temp dir, move result to final path."""
        gguf_path = paths.export_gguf_path(npc_key, model_id, quant)
        gguf_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=f"gguf_{npc_key}_") as tmpdir:
            print(f"[export] Generating GGUF ({quant}) in temp directory...")
            model.save_pretrained_gguf(
                tmpdir,
                tokenizer=tokenizer,
                quantization_method=quant,
            )
            gguf_files = sorted(Path(tmpdir).glob("*.gguf"))
            if not gguf_files:
                print(f"[export] ⚠  No GGUF file generated for {quant}, skipping")
                return None
            shutil.move(str(gguf_files[0]), str(gguf_path))

        size = gguf_path.stat().st_size
        if size > 1024 * 1024 * 1024:
            print(f"[export] → {gguf_path.name} ({size / 1e9:.2f} GB)")
        else:
            print(f"[export] → {gguf_path.name} ({size / 1e6:.0f} MB)")
        return str(gguf_path)

    print(f"\n[export] NPC: {npc_key}, Model: {model_id}")
    quant_path = _do_export(quantization)
    f16_path = _do_export("f16")

    print(f"[export] Export complete!")
    return quant_path or f16_path


def generate_dataset_from_spec(spec_path, output_path=None):
    """Refuse implicit template generation when no dataset exists."""
    raise RuntimeError(
        "No existing dataset found. Generate one explicitly with "
        "scripts/generate_dataset.py --technique notebooklm --notebooklm-input <export.jsonl>, "
        "--technique ollama, or --technique template."
    )


def main():
    parser = argparse.ArgumentParser(description="Unsloth training launcher")

    # Mode
    parser.add_argument("config_or_spec", nargs="?",
                        help="Path to YAML config or subject spec (with --from-spec)")
    parser.add_argument("--from-spec", action="store_true",
                        help="Treat config_or_spec as a subject spec and auto-generate dataset")
    parser.add_argument("--remote", choices=["colab"],
                        help="Generate remote training notebook instead of training locally")
    parser.add_argument("--drive-data-path", type=str, default=None,
                        help="Google Drive path to dataset JSONL for Colab drive mode. "
                             "Sets remote to 'colab' implicitly.")
    parser.add_argument("--drive-gguf-dir", type=str, default=None,
                        help="Google Drive directory to save GGUF exports. "
                             "Defaults to /content/drive/MyDrive/Unsloth/gguf/")

    # Data
    parser.add_argument("--data", "-d", help="Training data path (JSONL or HF dataset)")
    parser.add_argument("--val-data", help="Validation data path (optional)")

    # Model
    parser.add_argument("--model", "-m", help="HuggingFace model ID")
    available_presets = get_available_presets()
    parser.add_argument("--preset", choices=available_presets if available_presets else None,
                        help="Training preset (overrides YAML defaults)")

    # Training overrides
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--lr", type=float, dest="learning_rate", help="Learning rate")
    parser.add_argument("--epochs", type=int, dest="num_epochs", help="Number of epochs")
    parser.add_argument("--batch-size", type=int, dest="batch_size", help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, dest="gradient_accumulation_steps",
                        help="Gradient accumulation steps")
    parser.add_argument("--max-seq-len", type=int, dest="max_seq_length",
                        help="Max sequence length")
    parser.add_argument("--lora-r", type=int, help="LoRA rank")
    parser.add_argument("--lora-alpha", type=int, help="LoRA alpha")
    parser.add_argument("--lora-dropout", type=float, help="LoRA dropout")
    parser.add_argument("--neftune", type=float, dest="neftune_noise_alpha", help="NEFTune noise alpha")
    parser.add_argument("--weight-decay", type=float, dest="weight_decay", help="Weight decay")
    parser.add_argument("--warmup", type=int, dest="warmup_steps", help="Warmup steps")

    # Features
    parser.add_argument("--packing", type=lambda x: x.lower() == "true",
                        help="Enable packing (True/False)")
    parser.add_argument("--train-on-responses", type=lambda x: x.lower() == "true",
                        dest="train_on_responses_only",
                        help="Train on responses only (True/False)")
    parser.add_argument("--no-tensorboard", action="store_true",
                        help="Disable TensorBoard logging")

    # Export
    parser.add_argument("--export-gguf", action="store_true",
                        help="Export merged model to full GGUF after training")
    parser.add_argument("--export-lora", action="store_true",
                        help="Export only the LoRA adapter as GGUF (for LLMUnity runtime loading)")
    parser.add_argument("--quantization", default="q4_k_m",
                        help="GGUF quantization (default: q4_k_m)")

    # Validation/config display
    parser.add_argument("--show-presets", action="store_true",
                        help="Show available presets and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print config and exit without training")
    parser.add_argument("--tune", action="store_true",
                        help="Run hyperparameter optimization (grid search)")

    args = parser.parse_args()

    # Show presets and exit
    if args.show_presets:
        print("Available training presets:\n")
        for name in get_available_presets():
            desc = get_preset_description(name)
            print(f"  {name:15s}  {desc}")
        return

    # Determine config path and data path
    npc_key = "default"
    if args.config_or_spec and args.from_spec:
        # Load spec early for npc_key and dataset auto-detection
        with open(args.config_or_spec) as f:
            spec = json.load(f)
        npc_key = spec.get("npc_key", "default")
        # Auto-detect dataset if not explicitly provided
        if not args.data:
            detected = paths.autodetect_dataset(npc_key)
            if detected:
                technique, train_path, _ = detected
                data_path = str(train_path)
                print(f"[auto] Using existing dataset technique '{technique}': {data_path}")
            else:
                try:
                    data_path = generate_dataset_from_spec(args.config_or_spec)
                except RuntimeError as exc:
                    print(f"Error: {exc}")
                    sys.exit(2)
        else:
            data_path = args.data
        config_path = PROJECT_ROOT / "configs" / "lora-sft-base.yaml"
        if not config_path.exists():
            print(f"Error: Base config not found at {config_path}")
            sys.exit(1)
    elif args.config_or_spec and args.config_or_spec.endswith((".yaml", ".yml")):
        config_path = args.config_or_spec
        data_path = args.data
    else:
        # Direct CLI usage with no config file
        config_path = PROJECT_ROOT / "configs" / "lora-sft-base.yaml"
        data_path = args.data or args.config_or_spec
        if not config_path.exists():
            print("Error: No config.yaml found. Provide a config path or subject spec.")
            parser.print_help()
            sys.exit(1)

    if not data_path:
        print("Error: No training data specified. Use --data or --from-spec.")
        sys.exit(1)

    # Build overrides from CLI args
    cli_overrides = {
        "model": args.model,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "num_epochs": args.num_epochs,
        "learning_rate": args.learning_rate,
        "max_seq_length": args.max_seq_length,
        "output_dir": args.output,
        "lora_r": args.lora_r,
        "lora_alpha": args.lora_alpha,
        "lora_dropout": args.lora_dropout,
        "packing": args.packing,
        "train_on_responses_only": args.train_on_responses_only,
        "neftune_noise_alpha": args.neftune_noise_alpha,
        "weight_decay": args.weight_decay,
        "warmup_steps": args.warmup_steps,
    }

    # Load and resolve config
    config = load_config(config_path, preset=args.preset, overrides=cli_overrides)

    if args.no_tensorboard:
        config["logging"]["enable_tensorboard"] = False

    # ── Run ID experiment tracking ──────────────────────────────────────
    # Determine NPC key from output path or data path
    if args.output:
        npc_key = Path(args.output).name
    elif args.from_spec and args.config_or_spec:
        # npc_key already loaded from spec above
        pass

    # Generate a unique run ID and override the output directory
    run_id = paths.generate_run_id(npc_key, args.preset or "base")
    run_output_dir = paths.run_dir(npc_key, run_id)

    # Override output_dir with run-specific path (before printing config)
    config["training"]["output_dir"] = str(run_output_dir)

    print_config(config, preset_name=args.preset)
    print(f"  Run ID:      {run_id}")
    print("=" * 60)

    if args.dry_run:
        print("\n[Dry run] Configuration looks good. Pass --data to train.")
        return

    # Create the run-specific output directory
    os.makedirs(run_output_dir, exist_ok=True)

    # Save frozen config for reproducibility
    frozen_config_path = run_output_dir / "config.yaml"
    with open(frozen_config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    # Create/update latest symlink
    latest_link = paths.output_dir(npc_key) / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    os.symlink(f"runs/{run_id}", str(latest_link), target_is_directory=True)

    # ── Remote mode: generate Colab notebook instead of training ────────
    if args.remote == "colab" or args.drive_data_path:
        from scripts.colab import generate_colab_notebook

        # Determine data mode -- drive if --drive-data-path is provided
        data_mode = None
        drive_data_path = None
        drive_gguf_dir = None
        if args.drive_data_path:
            data_mode = "drive"
            drive_data_path = args.drive_data_path
            drive_gguf_dir = args.drive_gguf_dir

        # Load subject spec if available
        spec = None
        if args.from_spec and args.config_or_spec:
            from generate_dataset import load_subject_spec
            spec = load_subject_spec(args.config_or_spec)

        notebook_path = generate_colab_notebook(
            data_path=data_path,
            model_name=config.get("model", "unsloth/Llama-3.1-8B-Instruct-bnb-4bit"),
            preset_name=args.preset or "fast-8b",
            subject_spec=spec,
            output_dir=str(PROJECT_ROOT / "colab" / "outputs"),
            data_mode=data_mode,
            drive_data_path=drive_data_path,
            drive_gguf_dir=drive_gguf_dir,
        )
        return

    # ── Main training flow ──────────────────────────────────────────────
    start_time = time.time()

    if args.tune:
        print("\n" + "!" * 60)
        print("  HYPERPARAMETER OPTIMIZATION MODE")
        print("!" * 60)
        
        lrs = [1e-4, 2e-4, 5e-4]
        ranks = [16, 32, 64]
        best_loss = float('inf')
        best_cfg = None
        
        for lr in lrs:
            for rank in ranks:
                # Update config for this trial
                config["training"]["learning_rate"] = lr
                config["lora"]["lora_r"] = rank
                config["lora"]["lora_alpha"] = rank * 2
                
                trial_id = f"{run_id}_lr{lr}_r{rank}"
                trial_output_dir = paths.run_dir(npc_key, trial_id)
                config["training"]["output_dir"] = str(trial_output_dir)
                
                print(f"\n>>> Trial: LR={lr}, Rank={rank}")
                os.makedirs(trial_output_dir, exist_ok=True)
                
                # Load, train, and clear
                model, tokenizer = setup_model_and_tokenizer(config)
                dataset, eval_dataset, tokenizer = prepare_dataset(data_path, tokenizer, config)
                output_dir, trainer_stats = run_training(model, tokenizer, dataset, eval_dataset, config)
                
                loss = trainer_stats.training_loss
                if loss < best_loss:
                    best_loss = loss
                    best_cfg = (lr, rank)
                
                # Cleanup to avoid OOM
                import torch
                import gc
                del model
                del tokenizer
                gc.collect()
                torch.cuda.empty_cache()
                
        print(f"\n{'=' * 60}")
        print(f"  HPO COMPLETE")
        print(f"  Best config: LR={best_cfg[0]}, Rank={best_cfg[1]}")
        print(f"  Best loss:   {best_loss:.4f}")
        print(f"{'=' * 60}")
        return

    model, tokenizer = setup_model_and_tokenizer(config)

    dataset, eval_dataset, tokenizer = prepare_dataset(data_path, tokenizer, config)

    output_dir, trainer_stats = run_training(model, tokenizer, dataset, eval_dataset, config)

    elapsed = time.time() - start_time

    # Save experiment metrics
    metrics = {
        "training_loss": trainer_stats.training_loss,
        "run_id": run_id,
        "preset": args.preset,
        "model": config.get("model"),
        "npc_key": npc_key,
        "timestamp": datetime.now().isoformat(),
        "duration_minutes": round(elapsed / 60, 1),
    }
    metrics_path = run_output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # Save run manifest for reproducibility and comparisons
    dataset_sha256 = None
    try:
        h = hashlib.sha256()
        with open(data_path, "rb") as df:
            for chunk in iter(lambda: df.read(1024 * 1024), b""):
                h.update(chunk)
        dataset_sha256 = h.hexdigest()
    except Exception:
        dataset_sha256 = None

    git_commit = None
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(PROJECT_ROOT),
            text=True,
        ).strip()
    except Exception:
        git_commit = None

    val_data_path = None
    try:
        val_data_path = paths.infer_validation_path(str(data_path))
    except Exception:
        val_data_path = None

    run_manifest = {
        "run_id": run_id,
        "npc_key": npc_key,
        "created_at": datetime.now().isoformat(),
        "git_commit": git_commit,
        "preset": args.preset,
        "model_id": config.get("model"),
        "paths": {
            "run_output_dir": str(run_output_dir),
            "frozen_config": str(frozen_config_path),
            "metrics": str(metrics_path),
            "train_data": str(data_path),
            "validation_data": str(val_data_path) if val_data_path else None,
        },
        "dataset": {
            "technique": Path(data_path).parent.name,
            "train_sha256": dataset_sha256,
        },
        "results": {
            "training_loss": trainer_stats.training_loss,
            "duration_minutes": round(elapsed / 60, 1),
        },
    }

    run_manifest_path = run_output_dir / "run_manifest.json"
    with open(run_manifest_path, "w") as f:
        json.dump(run_manifest, f, indent=2)

    # Update "best" symlink (lowest training loss wins)
    current_loss = trainer_stats.training_loss
    best_loss = current_loss
    best_run = run_id
    for manifest_file in sorted(paths.run_dir(npc_key, "").parent.glob("*/run_manifest.json")):
        try:
            with open(manifest_file) as f:
                m = json.load(f)
            loss = m.get("results", {}).get("training_loss")
            if loss is not None and loss < best_loss:
                best_loss = loss
                best_run = m["run_id"]
        except Exception:
            pass
    best_link = paths.output_dir(npc_key) / "best"
    if best_link.exists() or best_link.is_symlink():
        best_link.unlink()
    os.symlink(f"runs/{best_run}", str(best_link), target_is_directory=True)
    print(f"  Best run:   {best_run} (loss={best_loss:.4f})")

    print(f"\n{'=' * 60}")
    print(f"  TRAINING COMPLETE")
    print(f"  Duration: {elapsed / 60:.1f} minutes")
    print(f"  Output:   {output_dir}")
    print(f"  Run ID:   {run_id}")
    print(f"  Manifest: {run_manifest_path}")
    print(f"{'=' * 60}")

    # Export to GGUF
    if args.export_gguf:
        export_to_gguf(model, tokenizer, output_dir, quantization=args.quantization)

    # Export LoRA adapter as GGUF (for LLMUnity runtime loading)
    if args.export_lora:
        from scripts.export_adapter import convert_adapter
        print(f"\n[export] Exporting LoRA adapter to GGUF (for LLMUnity)...")
        lora_out = convert_adapter(output_dir, outtype="f16")
        print(f"[export] LoRA adapter GGUF: {lora_out}")

    print("\nDone!")


if __name__ == "__main__":
    main()
