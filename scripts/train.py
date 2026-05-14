#!/usr/bin/env python3
"""
train.py — Unified Unsloth Training Launcher

This script manages the SFT (Supervised Fine-Tuning) process using Unsloth
and LoRA. It supports hierarchical configurations and model-aware presets.

Usage:
    ./ucore train subjects/chemistry_instructor.json --preset fast-3b
    python scripts/train.py subjects/chemistry_instructor.json --from-spec --export-gguf

Technical Details:
- Input: train_clean.jsonl and a subject spec or YAML config.
- Output: LoRA adapter weights in outputs/{npc_key}/runs/{run_id}/.
- Features: Support for packing, response-only training, and automatic GGUF export.
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


def check_promotion_rules(training_loss: float, config: dict, num_train_examples: int) -> tuple[bool, list[str]]:
    """Check if the model meets minimum quality thresholds for promotion to 'best'.

    Reads thresholds from configs/promotion-rules.yaml.
    Returns (passed, failure_reasons). Returns (True, []) if no rules file exists.
    """
    rules_path = PROJECT_ROOT / "configs" / "promotion-rules.yaml"
    if not rules_path.exists():
        return True, []

    with open(rules_path) as f:
        rules = yaml.safe_load(f) or {}

    failures = []
    loss_threshold = rules.get("max_training_loss", None)
    if loss_threshold is not None:
        if training_loss > loss_threshold:
            failures.append(
                f"Training loss {training_loss:.4f} exceeds threshold {loss_threshold:.4f}"
            )

    min_examples = rules.get("min_train_examples", None)
    if min_examples is not None:
        if num_train_examples < min_examples:
            failures.append(
                f"Only {num_train_examples} training examples, minimum is {min_examples}"
            )

    return len(failures) == 0, failures


def log_config_snapshot(config, run_dir):
    """Write a frozen snapshot of the merged config to the run directory."""
    snapshot_path = os.path.join(run_dir, "config_snapshot.yaml")
    try:
        with open(snapshot_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"  [WARN] Could not write config snapshot: {e}")


def estimate_vram(config: dict) -> tuple[float, str]:
    """Rough VRAM estimate based on model size and LoRA config.

    Returns (estimated_gb, notes).
    """
    model_name = config.get("model", "unknown")
    lora_r = config.get("lora_r", 16)
    max_seq = config.get("max_seq_length", 2048)
    packing = config.get("packing", True)

    # Rough per-parameter-size VRAM factors (bnb-4bit)
    estimated_gb = 8.0  # baseline for 1.7B-3B models
    if "8b" in model_name.lower() or "8B" in model_name:
        estimated_gb = 14.0
    elif "7b" in model_name.lower() or "7B" in model_name:
        estimated_gb = 12.0
    elif "3b" in model_name.lower() or "3B" in model_name:
        estimated_gb = 8.0
    elif "1b" in model_name.lower() or "1B" in model_name:
        estimated_gb = 4.0

    # Adjust for rank
    estimated_gb += (lora_r - 16) * 0.1
    # Adjust for seq len
    estimated_gb *= max_seq / 2048
    # Packing reduces memory
    if packing:
        estimated_gb *= 0.85

    notes = "Optimized for 24GB+ cards" if estimated_gb > 20 else "Fits 12GB+ cards"
    return round(estimated_gb, 1), notes


def get_model_name_from_spec(spec_path):
    """Extract a model name from the subject spec JSON."""
    spec_path = Path(spec_path)
    if not spec_path.exists():
        return None
    try:
        with open(spec_path) as f:
            spec = json.load(f)
        return spec.get("model", spec.get("llm", {}).get("model_name", None))
    except (json.JSONDecodeError, KeyError):
        return None


def get_config_from_spec(spec_path, preset=None, overrides=None):
    """Build a full training config from a subject spec JSON.

    The spec can define a base model, training parameters, and dataset technique.
    Preset YAML stacks on top; CLI overrides win.
    """
    spec_path = Path(spec_path)
    if not spec_path.exists():
        print(f"Error: Spec file not found: {spec_path}")
        sys.exit(1)

    with open(spec_path) as f:
        spec = json.load(f)

    npc_key = spec_path.stem

    # Determine technique from spec or default
    technique = spec.get("technique", spec.get("dataset", {}).get("technique", "notebooklm"))

    # Base model from spec (model_id) or spec.llm.model_name
    model_id = (
        spec.get("model")
        or spec.get("model_id")
        or spec.get("llm", {}).get("model_name")
        or spec.get("llm", {}).get("base_model")
        or "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
    )

    # Dataset path
    datasets_root = PROJECT_ROOT / "datasets" / npc_key / technique
    train_path = datasets_root / "train_clean.jsonl"
    if not train_path.exists():
        train_path = datasets_root / "train.jsonl"

    # Output dir
    output_dir = PROJECT_ROOT / "outputs" / npc_key

    config = {
        "npc_key": npc_key,
        "model": model_id,
        "dataset_path": str(train_path),
        "technique": technique,
        "output_dir": str(output_dir),
        "use_lora": True,
        "unsloth": True,
        "training": {
            "batch_size": 2,
            "gradient_accumulation_steps": 8,
            "num_epochs": 3,
            "learning_rate": 2e-4,
            "lr_scheduler_type": "cosine",
            "max_seq_length": 2048,
            "warmup_steps": 10,
            "packing": True,
            "train_on_responses_only": True,
            "save_steps": 50,
            "eval_steps": 50,
        },
        "lora": {
            "r": 16,
            "alpha": 32,
            "dropout": 0.0,
        },
        "logging": {
            "enable_tensorboard": True,
            "enable_wandb": False,
        },
    }

    if preset:
        preset_config = load_preset(preset)
        config = deep_merge(config, preset_config)

    if overrides:
        # Only set non-None overrides
        clean_overrides = {k: v for k, v in overrides.items() if v is not None}
        # Map CLI overrides to correct config paths
        override_map = {
            "model": ["model"],
            "batch_size": ["training", "batch_size"],
            "gradient_accumulation_steps": ["training", "gradient_accumulation_steps"],
            "num_epochs": ["training", "num_epochs"],
            "learning_rate": ["training", "learning_rate"],
            "lr_scheduler_type": ["training", "lr_scheduler_type"],
            "max_seq_length": ["training", "max_seq_length"],
            "output_dir": ["output_dir"],
            "lora_r": ["lora", "r"],
            "lora_alpha": ["lora", "alpha"],
            "lora_dropout": ["lora", "dropout"],
            "packing": ["training", "packing"],
            "train_on_responses_only": ["training", "train_on_responses_only"],
            "neftune_noise_alpha": ["training", "neftune_noise_alpha"],
            "weight_decay": ["training", "weight_decay"],
            "warmup_steps": ["training", "warmup_steps"],
        }
        for key, value in clean_overrides.items():
            if key in override_map:
                path_keys = override_map[key]
                target = config
                for pk in path_keys[:-1]:
                    if pk not in target:
                        target[pk] = {}
                    target = target[pk]
                target[path_keys[-1]] = value

    return config


def load_config(config_path, preset=None, overrides=None):
    """Load and resolve a YAML config, merging presets and CLI overrides."""
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    if preset:
        preset_config = load_preset(preset)
        config = deep_merge(config, preset_config)

    if overrides:
        for key, value in overrides.items():
            if value is not None:
                if key == "model":
                    config["model"] = value
                elif key == "output_dir":
                    config["output_dir"] = value
                elif key in ("batch_size", "gradient_accumulation_steps", "num_epochs", "learning_rate",
                             "max_seq_length"):
                    config.setdefault("training", {})
                    config["training"][key] = value
                elif key in ("lora_r", "lora_alpha", "lora_dropout"):
                    config.setdefault("lora", {})
                    config["lora"][key.replace("lora_", "")] = value
                elif key == "lr_scheduler_type":
                    config.setdefault("training", {})
                    config["training"]["lr_scheduler_type"] = value
                elif key == "packing":
                    config.setdefault("training", {})
                    config["training"]["packing"] = value
                elif key == "train_on_responses_only":
                    config.setdefault("training", {})
                    config["training"]["train_on_responses_only"] = value
                elif key == "neftune_noise_alpha":
                    config.setdefault("training", {})
                    config["training"]["neftune_noise_alpha"] = value
                elif key == "weight_decay":
                    config.setdefault("training", {})
                    config["training"]["weight_decay"] = value
                elif key == "warmup_steps":
                    config.setdefault("training", {})
                    config["training"]["warmup_steps"] = value
                else:
                    config[key] = value

    return config


def count_training_examples(path):
    """Count JSONL lines efficiently."""
    if not os.path.exists(path):
        return 0
    try:
        result = subprocess.run(
            ["wc", "-l", path], capture_output=True, text=True, timeout=10
        )
        return int(result.stdout.strip().split()[0])
    except Exception:
        return 0


def get_run_output_path(output_dir):
    """Create a run-specific output directory with an auto-incrementing run ID.

    Returns (run_dir_path, run_id) where run_id is like 'run_001'.
    """
    output_dir = Path(output_dir)
    runs_dir = output_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Find highest existing run number
    existing_runs = [
        d for parent in (output_dir, runs_dir) if parent.exists()
        for d in parent.iterdir() if d.is_dir() and d.name.startswith("run_")
    ]
    max_num = 0
    for d in existing_runs:
        try:
            num = int(d.name.split("_")[1])
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            pass

    run_id = max_num + 1
    run_dir = runs_dir / f"run_{run_id:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)

    return str(run_dir), f"run_{run_id:03d}"


def get_model_and_tokenizer(config):
    """Load the base model and tokenizer via Unsloth."""
    from unsloth import FastLanguageModel

    model_name = config.get("model", "unsloth/Llama-3.2-3B-Instruct-bnb-4bit")
    max_seq_length = config.get("training", {}).get("max_seq_length", 2048)
    use_lora = config.get("use_lora", True)
    lora_config = config.get("lora", {})

    print(f"  Loading model: {model_name}")
    print(f"  Max seq length: {max_seq_length}")
    if use_lora:
        print(f"  LoRA rank: {lora_config.get('r', 16)}, alpha: {lora_config.get('alpha', 32)}")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    if use_lora:
        model = FastLanguageModel.get_peft_model(
            model,
            r=lora_config.get("r", 16),
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_alpha=lora_config.get("alpha", 32),
            lora_dropout=lora_config.get("dropout", 0),
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=42,
            use_rslora=False,
            loftq_config=None,
        )

    return model, tokenizer


def load_dataset_from_jsonl(path, tokenizer, config):
    """Load and tokenize a JSONL dataset."""
    from datasets import Dataset

    max_seq_length = config.get("training", {}).get("max_seq_length", 2048)
    packing = config.get("training", {}).get("packing", True)

    print(f"  Loading dataset from: {path}")
    if not os.path.exists(path):
        print(f"  [ERROR] Dataset not found: {path}")
        sys.exit(1)

    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    row = json.loads(line)
                    text = row.get("text", "")

                    # Preferred modern format: ChatML messages
                    if not text and isinstance(row.get("messages"), list):
                        messages = row.get("messages", [])
                        if hasattr(tokenizer, "apply_chat_template"):
                            text = tokenizer.apply_chat_template(
                                messages,
                                tokenize=False,
                                add_generation_prompt=False,
                            )
                        else:
                            # Fallback: naive role/content join
                            chunks = []
                            for m in messages:
                                role = m.get("role", "")
                                content = m.get("content", "")
                                if role and content:
                                    chunks.append(f"{role}: {content}")
                            text = "\n".join(chunks)

                    if isinstance(text, str) and text.strip():
                        rows.append({"text": text})
                except json.JSONDecodeError:
                    continue

    if not rows:
        print("  [ERROR] No valid training examples found in dataset.")
        sys.exit(1)

    print(f"  Loaded {len(rows)} training examples")
    return Dataset.from_list(rows)


def run_training(model, tokenizer, dataset, eval_dataset, config):
    """Run the SFT training loop."""
    from trl import SFTTrainer
    from transformers import TrainingArguments
    import torch

    training = config.get("training", {})
    output_dir = training.get("output_dir", str(PROJECT_ROOT / "outputs" / "default"))
    print(f"  Output: {os.path.relpath(output_dir, PROJECT_ROOT)}")
    os.makedirs(output_dir, exist_ok=True)

    # Report targets
    report_targets = []
    if config.get("logging", {}).get("enable_tensorboard", True):
        report_targets.append("tensorboard")
    if config.get("wandb", {}).get("enabled", False):
        report_targets.append("wandb")
    report_to = report_targets if report_targets else "none"

    args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=training.get("num_epochs", 3),
        max_steps=training.get("max_steps", -1) if training.get("max_steps", -1) > 0 else -1,
        per_device_train_batch_size=training.get("batch_size", 1),
        gradient_accumulation_steps=training.get("gradient_accumulation_steps", 8),
        warmup_steps=training.get("warmup_steps", 10),
        learning_rate=training.get("learning_rate", 2e-4),
        lr_scheduler_type=training.get("lr_scheduler_type", "cosine"),
        weight_decay=training.get("weight_decay", 0.01),
        neftune_noise_alpha=training.get("neftune_noise_alpha", None),
        logging_steps=1,
        save_steps=training.get("save_steps", 50),
        eval_steps=training.get("eval_steps", 50),
        eval_strategy="steps" if eval_dataset else "no",
        save_total_limit=3,
        load_best_model_at_end=True if eval_dataset else False,
        report_to=report_to,
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

    # Apply train_on_responses_only to mask user tokens in loss when available.
    if training.get("train_on_responses_only", False) and hasattr(tokenizer, "apply_chat_template"):
        if hasattr(trainer, "train_on_responses_only"):
            print("  [INFO] Applying train_on_responses_only")
            trainer.train_on_responses_only()
        else:
            print("  [WARN] train_on_responses_only requested, but current trainer API does not expose it; continuing without response-only masking")

    print(f"  Starting training ({training.get('num_epochs', 3)} epochs, {training.get('batch_size', 1)} batch)...")
    train_result = trainer.train()

    # Save the final model
    print("  Saving model...")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Save training metrics
    metrics = {}
    if train_result:
        metrics = train_result.metrics
    with open(os.path.join(output_dir, "training_metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    return trainer, metrics


def _should_push_gguf_to_hub(export_config):
    """Return True only when GGUF Hub upload was explicitly configured."""
    return bool(export_config.get("push_to_hub") and export_config.get("hub_repo_id"))


def _assert_valid_hub_export_config(export_config):
    """Fail loudly for explicit Hub uploads missing a destination repo."""
    if export_config.get("push_to_hub") and not export_config.get("hub_repo_id"):
        raise RuntimeError("export.push_to_hub is true, but export.hub_repo_id is missing")


def _move_generated_gguf(temp_dir, output_path):
    """Move Unsloth's generated GGUF from a temporary export dir."""
    output_path = Path(output_path)
    gguf_files = sorted(Path(temp_dir).rglob("*.gguf"))
    sibling_dir = Path(f"{temp_dir}_gguf")

    if not gguf_files and sibling_dir.exists():
        gguf_files = sorted(sibling_dir.rglob("*.gguf"))

    if not gguf_files:
        raise RuntimeError(f"No GGUF file generated in {temp_dir}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(gguf_files[0]), str(output_path))
    return output_path


def export_to_gguf(model, tokenizer, config, output_path, quantization=None):
    """Export the fine-tuned model to a local GGUF file unless Hub upload is explicit."""
    from unsloth import FastLanguageModel

    export_config = config.get("export", {})
    quantization = quantization or export_config.get("quantization", "q4_k_m")

    print(f"  Exporting to GGUF (quant={quantization})...")
    print(f"  Output: {output_path}")

    FastLanguageModel.for_inference(model)

    _assert_valid_hub_export_config(export_config)

    if _should_push_gguf_to_hub(export_config):
        hub_repo_id = export_config.get("hub_repo_id")
        model.push_to_hub_gguf(hub_repo_id, tokenizer, quantization)
        return sorted(Path(output_path).parent.glob("*.gguf"))

    if not hasattr(model, "save_pretrained_gguf"):
        raise RuntimeError("Loaded model does not support local GGUF export via save_pretrained_gguf")

    with tempfile.TemporaryDirectory(prefix="train_gguf_export_") as temp_dir:
        model.save_pretrained_gguf(
            temp_dir,
            tokenizer=tokenizer,
            quantization_method=quantization,
        )
        generated_path = _move_generated_gguf(temp_dir, output_path)

    return [generated_path]


def main():
    parser = argparse.ArgumentParser(description="Unsloth training launcher")

    # Mode
    parser.add_argument("config_or_spec", nargs="?",
                        help="Path to YAML config or subject spec (with --from-spec)")
    parser.add_argument("--from-spec", action="store_true",
                        help="Interpret config_or_spec as a subject spec JSON")
    parser.add_argument("--technique", choices=["docs", "notebooklm", "ollama", "template", "openai", "anthropic"],
                        help="Override dataset technique when training from spec")

    # Logging / output
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-essential output")

    # Preset
    available_presets = get_available_presets()
    parser.add_argument("--preset", choices=available_presets if available_presets else None,
                        help="Training preset (overrides YAML defaults)")

    # Training overrides
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--model", help="Base model ID/path override")
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
    parser.add_argument("--lr-scheduler", dest="lr_scheduler_type",
                        choices=["cosine", "linear", "constant"],
                        help="Learning rate scheduler type")

    # Features
    parser.add_argument("--packing", type=lambda x: x.lower() == "true",
                        help="Enable packing (True/False)")
    parser.add_argument("--train-on-responses", type=lambda x: x.lower() == "true",
                        dest="train_on_responses_only",
                        help="Train on responses only (True/False)")
    parser.add_argument("--no-tensorboard", action="store_true",
                        help="Disable TensorBoard logging")
    parser.add_argument("--wandb", action="store_true", default=None,
                        help="Enable W&B logging (overrides config)")
    parser.add_argument("--no-wandb", action="store_true", default=None,
                        dest="disable_wandb", help="Disable W&B logging (overrides config)")

    # Export
    parser.add_argument("--export-gguf", action="store_true",
                        help="Export trained model to GGUF after training")
    parser.add_argument("--quantization", default=None, choices=["q4_k_m", "q5_k_m", "q8_0", "f16"],
                        help="GGUF quantization type (default: q4_k_m)")

    args = parser.parse_args()

    # ── Dispatch ────────────────────────────────────────────────────────
    if not args.config_or_spec:
        parser.print_help()
        sys.exit(1)

    config_path = args.config_or_spec
    if not args.from_spec and Path(config_path).suffix.lower() == ".json":
        args.from_spec = True

    # Determine technique if --from-spec is used (also used for dataset path decisions)
    # Build cli_overrides for get_config_from_spec
    cli_overrides = {
        "model": args.model if hasattr(args, 'model') else None,
        "batch_size": args.batch_size,
        "gradient_accumulation_steps": args.gradient_accumulation_steps,
        "num_epochs": args.num_epochs,
        "learning_rate": args.learning_rate,
        "lr_scheduler_type": args.lr_scheduler_type,
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

    if args.from_spec:
        config = get_config_from_spec(config_path, preset=args.preset, overrides=cli_overrides)
    else:
        # Standard load_config for YAML
        config = load_config(config_path, preset=args.preset, overrides=cli_overrides)

    if args.technique:
        config["technique"] = args.technique
        npc_for_path = config.get("npc_key", Path(config_path).stem)
        clean_path = PROJECT_ROOT / "datasets" / npc_for_path / args.technique / "train_clean.jsonl"
        raw_path = PROJECT_ROOT / "datasets" / npc_for_path / args.technique / "train.jsonl"
        config["dataset_path"] = str(clean_path if clean_path.exists() else raw_path)

    if args.no_tensorboard:
        config["logging"]["enable_tensorboard"] = False

    # CLI wandb override
    if args.wandb:
        config["wandb"] = config.get("wandb", {})
        config["wandb"]["enabled"] = True
    elif args.disable_wandb:
        config["wandb"] = config.get("wandb", {})
        config["wandb"]["enabled"] = False

    # Print config summary
    npc_key = config.get("npc_key", "unknown")
    model_name = config.get("model", "unknown")
    technique = config.get("technique", "unknown")
    lora_r = config.get("lora", {}).get("r", config.get("training", {}).get("lora_r", "?"))
    lora_alpha_val = config.get("lora", {}).get("alpha", config.get("training", {}).get("lora_alpha", "?"))
    vram_gb, vram_notes = estimate_vram(config)

    print(f"\n{'='*60}")
    print(f"  Unsloth Training Launcher")
    print(f"{'='*60}")
    print(f"  NPC:            {npc_key}")
    print(f"  Model:          {model_name}")
    print(f"  Technique:      {technique}")
    print(f"  LoRA Rank:      {lora_r}")
    print(f"  LoRA Alpha:     {lora_alpha_val}")
    print(f"  LR Scheduler:   {config.get('training', {}).get('lr_scheduler_type', 'cosine')}")
    print(f"  Estimated VRAM: {vram_gb}GB ({vram_notes})")
    print(f"  Preset:         {args.preset or 'none'}")
    print(f"  W&B:            {'enabled' if config.get('wandb', {}).get('enabled') else 'disabled'}")
    print(f"  Export GGUF:    {'yes' if args.export_gguf else 'no'}")
    print(f"{'='*60}\n")

    # ── Resolve output paths ───────────────────────────────────────────
    output_dir = config.get("output_dir")
    if output_dir:
        run_dir, run_id = get_run_output_path(output_dir)
    else:
        run_dir, run_id = get_run_output_path(str(PROJECT_ROOT / "outputs" / npc_key))

    config.setdefault("training", {})["output_dir"] = run_dir
    config["run_id"] = run_id

    # Write config snapshot
    log_config_snapshot(config, run_dir)

    # ── Load model ─────────────────────────────────────────────────────
    print("  [1/4] Loading model and tokenizer...")
    model, tokenizer = get_model_and_tokenizer(config)
    print(f"  ✓ Model loaded")

    # ── Load dataset ───────────────────────────────────────────────────
    print("  [2/4] Loading dataset...")
    dataset_path = config.get("dataset_path", "")
    if not dataset_path or not os.path.exists(dataset_path):
        # Try to derive dataset path
        technique = config.get("technique", "template")
        clean_candidate = PROJECT_ROOT / "datasets" / npc_key / technique / "train_clean.jsonl"
        raw_candidate = PROJECT_ROOT / "datasets" / npc_key / technique / "train.jsonl"
        dataset_path = str(clean_candidate if clean_candidate.exists() else raw_candidate)

    dataset = load_dataset_from_jsonl(dataset_path, tokenizer, config)
    eval_dataset = None  # TODO: support eval split
    num_examples = len(dataset)
    print(f"  ✓ Dataset loaded: {num_examples} examples")

    # ── Training ───────────────────────────────────────────────────────
    print("  [3/4] Running training...")
    trainer, metrics = run_training(model, tokenizer, dataset, eval_dataset, config)
    training_loss = metrics.get("train_loss", 0.0)
    print(f"  ✓ Training complete: loss={training_loss:.4f}")

    # ── Promotion check ────────────────────────────────────────────────
    promotion_passed, promotion_failures = check_promotion_rules(
        training_loss, config, num_examples
    )
    if promotion_passed:
        print("  ✓ Promotion rules passed")
        # Create/update 'best' symlink to this run
        best_link = Path(output_dir or PROJECT_ROOT / "outputs" / npc_key) / "best"
        if best_link.exists() or best_link.is_symlink():
            best_link.unlink()
        try:
            best_link.symlink_to(Path("runs") / run_id)
            print(f"  ✓ Updated 'best' symlink → runs/{run_id}")
        except OSError:
            pass
    else:
        print(f"  ⚠ Promotion rules failed:")
        for failure in promotion_failures:
            print(f"    - {failure}")

    # Always update 'latest' symlink regardless of promotion result
    latest_link = Path(output_dir or PROJECT_ROOT / "outputs" / npc_key) / "latest"
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    try:
        latest_link.symlink_to(Path("runs") / run_id)
        print(f"  ✓ Updated 'latest' symlink → runs/{run_id}")
    except OSError:
        pass

    # ── GGUF Export ────────────────────────────────────────────────────
    if args.export_gguf:
        print("  [4/4] Exporting to GGUF...")
        exports_dir = paths.export_dir(npc_key)
        exports_dir.mkdir(parents=True, exist_ok=True)

        quantization = args.quantization or config.get("export", {}).get("quantization", "q4_k_m")

        gguf_path = str(paths.export_gguf_path(npc_key, config.get("model", "model"), quantization))

        gguf_files = export_to_gguf(model, tokenizer, config, gguf_path, quantization)

        print(f"  ✓ GGUF export complete:")
        for gf in gguf_files:
            size_mb = os.path.getsize(gf) / (1024 * 1024)
            print(f"    - {gf} ({size_mb:.1f} MB)")
        print(f"  ├ Saved to: {exports_dir}")

        # Write manifest
        manifest = {
            "npc_key": npc_key,
            "run_id": run_id,
            "base_model": config.get("model"),
            "technique": technique,
            "training_loss": training_loss,
            "num_examples": num_examples,
            "quantization": quantization,
            "lora_r": lora_r,
            "lora_alpha": lora_alpha_val,
            "created_at": datetime.now().isoformat(),
            "gguf_files": [str(gf) for gf in gguf_files],
        }
        manifest_path = exports_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"  ├ Manifest: {manifest_path}")
    else:
        print("  [4/4] Skipping GGUF export (use --export-gguf to enable)")

    print(f"\n{'='*60}")
    print(f"  Training complete!")
    print(f"  Run ID:  {run_id}")
    print(f"  Output:  {run_dir}")
    if args.export_gguf:
        exports_dir = PROJECT_ROOT / "exports" / npc_key
        print(f"  Exports: {exports_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
