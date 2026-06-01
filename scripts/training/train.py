#!/usr/bin/env python3
"""
train.py — Unified Unsloth Training Launcher

This script manages the SFT (Supervised Fine-Tuning) process using Unsloth
and LoRA. It supports hierarchical configurations and model-aware presets.

Usage:
    ./ucore train subjects/NPC_specs/chemistry_instructor.json --preset fast-3b
    python scripts/training/train.py subjects/NPC_specs/chemistry_instructor.json --from-spec --export-gguf

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

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from _config.workflow_context import resolve_workflow_context
from _config.log_setup import log_info, log_warn, log_error, log_state
from scripts.dataset.dataset_contracts import file_sha256
from scripts.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path
from scripts.ops.preflight import query_gpu_memory, run_preflight
from scripts.ops.model_presets import resolve_training_preset

# ── Model-size-aware presets ────────────────────────────────────────────────
# Each preset overrides the base YAML config for specific model sizes.
# Effective batch size = batch_size * gradient_accumulation_steps.
# Target: 16 for stable convergence (per QLoRA paper), adjusted for 6GB VRAM.
# Presets are loaded from configs/presets/ as override-only YAML files.
PRESETS_DIR = PROJECT_ROOT / "configs" / "presets"  # TODO: consider centralizing

_TOKENIZER_PLACEHOLDER_MAP = {
    "<EOS_TOKEN>": "eos_token",
    "<PAD_TOKEN>": "pad_token",
}


def _patch_tokenizers_backend_special_tokens(tokenizer) -> None:
    """Map TRL placeholder special tokens onto the real tokenizer ids.

    Some recent TRL/Unsloth combinations validate the literal placeholder tokens
    <EOS_TOKEN> and <PAD_TOKEN> against the tokenizer vocab before preparing the
    dataset. The underlying tokenizer already has real EOS/PAD tokens; we map the
    placeholders to those ids so validation succeeds without resizing embeddings.
    """
    tokenizer_cls = tokenizer.__class__
    if getattr(tokenizer_cls, "_unsloth_special_token_patch", False):
        return

    original_convert = tokenizer_cls.convert_tokens_to_ids

    def convert_tokens_to_ids(self, token):
        if token in _TOKENIZER_PLACEHOLDER_MAP:
            target_attr = _TOKENIZER_PLACEHOLDER_MAP[token]
            target_token = getattr(self, target_attr, None)
            if target_token:
                target_id = original_convert(self, target_token)
                if target_id is not None:
                    return target_id
        return original_convert(self, token)

    tokenizer_cls.convert_tokens_to_ids = convert_tokens_to_ids
    tokenizer_cls._unsloth_special_token_patch = True


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


def ensure_wandb_noninteractive(config: dict) -> None:
    """Prevent W&B-enabled presets from crashing unattended Colab runs.

    HuggingFace Trainer initializes W&B at train start. If a preset enables W&B
    but Colab has no API key configured, wandb raises UsageError instead of
    prompting cleanly inside subprocess output capture. Fall back to offline mode
    so training and GGUF export complete; users can `wandb sync` later.
    """
    if not config.get("wandb", {}).get("enabled", False):
        return

    mode = (os.environ.get("WANDB_MODE") or "").strip().lower()
    if mode in {"offline", "disabled", "dryrun"}:
        return

    if os.environ.get("WANDB_API_KEY"):
        return

    if (Path.home() / ".netrc").exists():
        return

    os.environ["WANDB_MODE"] = "offline"
    print("  [WARN] W&B enabled but no WANDB_API_KEY or ~/.netrc was found; using WANDB_MODE=offline so training will not crash.")


def init_wandb_tracking(config: dict, *, npc_key: str, technique: str, preset_name: str, run_id: str, output_dir: str,
                        project: str | None = None, entity: str | None = None):
    """Initialize W&B with a consistent training naming/tagging scheme."""
    if not config.get("wandb", {}).get("enabled", False):
        return None

    import wandb

    training_cfg = config.get("training", {}) if isinstance(config.get("training", {}), dict) else {}
    lora_cfg = config.get("lora", {}) if isinstance(config.get("lora", {}), dict) else {}
    dataset_path = config.get("dataset_path")
    dataset_sha256 = None
    quality_summary = None
    if dataset_path and os.path.isfile(dataset_path):
        try:
            dataset_sha256 = file_sha256(dataset_path)
        except Exception as e:
            dataset_sha256 = None
        summary_path = Path(dataset_path).parent / "quality_summary.json"
        if summary_path.exists():
            try:
                with summary_path.open(encoding="utf-8") as handle:
                    raw_summary = json.load(handle)
                quality_summary = {
                    "path": str(summary_path),
                    "status": raw_summary.get("status"),
                    "mode": raw_summary.get("quality_gate_mode"),
                    "pass_rate": raw_summary.get("pass_rate"),
                    "total": raw_summary.get("total"),
                    "failed": raw_summary.get("failed"),
                    "dataset_hash": (raw_summary.get("dataset_summary") or {}).get("content_sha256"),
                    "distribution_gaps": raw_summary.get("distribution_gaps"),
                }
            except Exception as e:
                quality_summary = {"path": str(summary_path), "status": "unreadable"}

    try:
        config_hash = hashlib.sha256(
            json.dumps(config, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    except Exception as e:
        config_hash = None

    batch_size = training_cfg.get("batch_size")
    grad_accum = training_cfg.get("gradient_accumulation_steps")
    effective_batch_size = None
    try:
        effective_batch_size = int(batch_size or 0) * int(grad_accum or 0)
    except Exception as e:
        pass

    wandb_cfg = {
        "npc_key": npc_key,
        "technique": technique,
        "preset": preset_name,
        "run_id": run_id,
        "output_dir": output_dir,
        "model": config.get("model"),
        "dataset_path": dataset_path,
        "dataset_sha256": dataset_sha256,
        "dataset_quality": quality_summary,
        "config_hash": config_hash,
        "training": training_cfg,
        "lora": lora_cfg,
        "effective_batch_size": effective_batch_size,
        "lora_r": lora_cfg.get("r", training_cfg.get("lora_r")),
        "lora_alpha": lora_cfg.get("alpha", training_cfg.get("lora_alpha")),
        "lora_dropout": lora_cfg.get("dropout", training_cfg.get("lora_dropout")),
        "lora_target_modules": lora_cfg.get("target_modules"),
        "learning_rate": training_cfg.get("learning_rate"),
        "batch_size": batch_size,
        "gradient_accumulation_steps": grad_accum,
        "num_epochs": training_cfg.get("num_epochs"),
        "max_seq_length": training_cfg.get("max_seq_length"),
        "lr_scheduler_type": training_cfg.get("lr_scheduler_type"),
        "weight_decay": training_cfg.get("weight_decay"),
        "warmup_steps": training_cfg.get("warmup_steps"),
        "packing": training_cfg.get("packing"),
        "train_on_responses_only": training_cfg.get("train_on_responses_only"),
        "full_config": config,
    }
    base_tags = [tag for tag in (config.get("wandb", {}).get("tags") or []) if tag]
    tags = list(dict.fromkeys(["train", npc_key, technique, preset_name, *base_tags]))
    group = os.environ.get("WANDB_RUN_GROUP") or os.environ.get("WANDB_GROUP") or npc_key

    run = wandb.init(
        project=project or config.get("wandb", {}).get("project", "unsloth-core"),
        entity=entity or config.get("wandb", {}).get("entity"),
        group=group,
        job_type="train",
        config=wandb_cfg,
        name=f"train-{npc_key}-{technique}-{preset_name}-{run_id}",
        tags=tags,
    )
    if run and getattr(run, "url", None):
        print(f"  [wandb] Run URL: {run.url}")
    define_metric = getattr(wandb, "define_metric", None)
    if callable(define_metric):
        try:
            define_metric("train/final_loss", summary="min")
        except Exception as e:
            pass
    return run


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

    rules_block = rules.get("thresholds", rules)

    failures = []
    loss_threshold = rules_block.get("max_training_loss", None)
    if loss_threshold is not None:
        if training_loss > loss_threshold:
            failures.append(
                f"Training loss {training_loss:.4f} exceeds threshold {loss_threshold:.4f}"
            )

    min_eff_batch = rules_block.get("min_eff_batch_size", None)
    if min_eff_batch is not None:
        training_cfg = config.get("training", {}) if isinstance(config, dict) else {}
        batch_size = int(training_cfg.get("batch_size", 1) or 1)
        grad_accum = int(training_cfg.get("gradient_accumulation_steps", 1) or 1)
        eff_batch = batch_size * grad_accum
        if eff_batch < int(min_eff_batch):
            failures.append(
                f"Effective batch size {eff_batch} is below minimum {int(min_eff_batch)}"
            )

    min_examples = rules_block.get("min_train_examples", None)
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


def update_run_pointer(pointer_path: Path, target: Path, label: str) -> bool:
    """Atomically refresh a run pointer symlink.

    The training layout expects outputs/<npc>/best and outputs/<npc>/latest to
    point at outputs/<npc>/runs/<run_id>. If a stale directory or file already
    exists, remove it first so a new training run can always refresh the pointer.
    """
    try:
        if pointer_path.exists() or pointer_path.is_symlink():
            if pointer_path.is_dir() and not pointer_path.is_symlink():
                shutil.rmtree(pointer_path)
            else:
                pointer_path.unlink()
        pointer_path.symlink_to(target)
        log_info("Updated '%s' symlink → %s", label, target)
        return True
    except OSError as exc:
        log_warn("Could not update '%s' symlink at %s: %s", label, pointer_path, exc)
        return False


def resolve_dataset_path(config: dict, npc_key: str) -> str:
    """Resolve the training JSONL path from config and repository layout."""
    dataset_path = config.get("dataset_path", "")
    if dataset_path and os.path.exists(dataset_path):
        return str(dataset_path)

    preferred_technique = config.get("technique")
    _, resolved_path, _ = paths.resolve_dataset_context(npc_key, preferred_technique)
    return str(resolved_path)


def validation_dataset_path(dataset_path: str | Path) -> Path | None:
    """Return the best sibling validation split for a training dataset."""
    dataset_path = Path(dataset_path)
    candidates = []
    if dataset_path.name == "train_clean.jsonl":
        candidates.append(dataset_path.with_name("validation_clean.jsonl"))
    candidates.append(dataset_path.with_name("validation.jsonl"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def dataset_quality_gate_errors(dataset_path: str | Path) -> list[str]:
    """Validate that DeepEval passed for this exact sanitized train dataset."""
    dataset_path = Path(dataset_path)
    summary_path = dataset_path.parent / "quality_summary.json"
    errors: list[str] = []

    if dataset_path.name != "train_clean.jsonl":
        errors.append(f"dataset is not sanitized train_clean.jsonl: {dataset_path}")
    if not dataset_path.exists():
        errors.append(f"dataset does not exist: {dataset_path}")
        return errors
    if not summary_path.exists():
        errors.append(f"quality summary is missing: {summary_path}")
        return errors

    try:
        with summary_path.open(encoding="utf-8") as handle:
            summary = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"quality summary is unreadable: {summary_path} ({exc})"]

    gate_mode = summary.get("quality_gate_mode") or "release"
    if gate_mode not in {"fast", "release"}:
        errors.append(f"quality summary has unknown quality_gate_mode {gate_mode!r}")
    if summary.get("status") != "ok":
        errors.append(f"quality summary status is {summary.get('status')!r}, expected 'ok'")
    if int(summary.get("total", 0) or 0) <= 0:
        errors.append("quality summary has no evaluated test cases")
    if gate_mode != "fast" and int(summary.get("failed", 0) or 0) > 0:
        errors.append(f"quality summary still has {summary.get('failed')} failing DeepEval cases")
    if summary.get("distribution_gaps"):
        errors.append("quality summary reports category distribution gaps")
    sanitizer_issues = summary.get("sanitizer_quality_issues") or []
    if sanitizer_issues:
        errors.append("quality summary reports sanitizer quality issues: " + "; ".join(str(issue) for issue in sanitizer_issues))
    unknown_rows = summary.get("dataset_unknown_rows")
    if unknown_rows is None:
        unknown_rows = (summary.get("dataset_summary") or {}).get("unknown_rows", 0)
    if int(unknown_rows or 0) > 0:
        errors.append(f"quality summary reports {unknown_rows} unknown dataset rows")

    recorded_hash = (summary.get("dataset_summary") or {}).get("content_sha256")
    current_hash = file_sha256(dataset_path)
    if not recorded_hash:
        errors.append("quality summary has no sanitized dataset hash; rerun dataset-eval")
    elif recorded_hash != current_hash:
        errors.append("quality summary does not match the current sanitized dataset hash")
    return errors


def estimate_vram(config: dict) -> tuple[float, str]:
    """Rough VRAM estimate based on model size and LoRA config.

    Returns (estimated_gb, notes).
    """
    model_name = config.get("model", "unknown")
    lora_cfg = config.get("lora", {}) if isinstance(config, dict) else {}
    training_cfg = config.get("training", {}) if isinstance(config, dict) else {}
    lora_r = config.get("lora_r", lora_cfg.get("r", lora_cfg.get("lora_r", 16)))
    max_seq = config.get("max_seq_length", training_cfg.get("max_seq_length", 2048))
    packing = config.get("packing", training_cfg.get("packing", True))

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

    ctx = resolve_workflow_context(spec_path, preset=preset)
    spec = ctx.spec
    npc_key = ctx.npc_key
    technique = ctx.technique
    train_path = ctx.dataset_path
    model_id = ctx.model_id
    resolved_preset = ctx.preset

    # Dataset path
    if train_path.name != "train_clean.jsonl":
        clean_candidate = train_path.with_name("train_clean.jsonl")
        if clean_candidate.exists():
            train_path = clean_candidate
    if not train_path.exists():
        _, train_path, _ = paths.resolve_dataset_context(npc_key, technique)
    
    # Try versioned dataset path first
    versioned = paths.dataset_latest_train_path(npc_key, technique)
    if versioned and versioned.exists():
        train_path = versioned

    # Verify dataset integrity before training
    from scripts.ops.stage_gate import verify_inputs
    missing = verify_inputs("train", [train_path] if train_path else [])
    if missing:
        print(f"  [error] Dataset not found for training: {missing[0]}")
        print(f"  [error] Please run: ./ucore generate {npc_key} --technique {technique}")
        return 1

    # Output dir
    output_dir = paths.output_dir(npc_key)

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

    if resolved_preset:
        preset_config = load_preset(resolved_preset)
        config = deep_merge(config, preset_config)

    config["preset"] = resolved_preset

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

    effective_model = (overrides or {}).get("model") or config.get("model")
    resolved_preset = resolve_training_preset(
        effective_model,
        preset=preset,
        spec_preset=config.get("preset") or config.get("training", {}).get("preset"),
    )
    if resolved_preset:
        preset_config = load_preset(resolved_preset)
        config = deep_merge(config, preset_config)

    config["preset"] = resolved_preset

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
    except Exception as e:
        return 0


def get_run_output_path(output_dir, preset_name="default", model_name=None):
    """Create a run-specific output directory using canonical run ID.

    Returns (run_dir_path, run_id) where run_id follows the canonical
    {YYYYMMDD}_{preset}_{model_short}_{sequential_number} format.
    """
    from _config.paths import generate_run_id, model_short_name
    output_dir = Path(output_dir)
    npc_key = output_dir.name
    
    track_name = preset_name
    if model_name:
        short = model_short_name(model_name)
        track_name = f"{preset_name}_{short}"
        
    run_id = generate_run_id(npc_key, track_name)
    run_dir = output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return str(run_dir), run_id


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
    print(f"  GPU memory utilization: {config.get('training', {}).get('gpu_memory_utilization', 0.9)}")

    gpu_memory_utilization = float(config.get("training", {}).get("gpu_memory_utilization", 0.9))

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
        device_map="auto",
        gpu_memory_utilization=gpu_memory_utilization,
    )
    _patch_tokenizers_backend_special_tokens(tokenizer)
    # Ensure tokenizer.eos_token/pad_token strings are the real values,
    # not placeholder strings that Unsloth's patching may have injected.
    tokenizer.eos_token = tokenizer.convert_ids_to_tokens(tokenizer.eos_token_id)
    tokenizer.pad_token = tokenizer.convert_ids_to_tokens(tokenizer.pad_token_id)

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


def load_dataset_from_jsonl(path, tokenizer, config, label="training"):
    """Load and tokenize a JSONL dataset."""
    from datasets import Dataset

    max_seq_length = config.get("training", {}).get("max_seq_length", 2048)
    packing = config.get("training", {}).get("packing", True)

    log_info("Loading dataset from: %s", path)
    if not os.path.exists(path):
        log_error("Dataset not found: %s", path)
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

    print(f"  Loaded {len(rows)} {label} examples")
    return Dataset.from_list(rows)


def run_training(model, tokenizer, dataset, eval_dataset, config, preset_name: str = "default"):
    """Run the SFT training loop."""
    from trl import SFTTrainer, SFTConfig
    import torch

    training = config.get("training", {})
    output_dir = training.get("output_dir", str(paths.output_dir("default")))
    print(f"  Output: {os.path.relpath(output_dir, PROJECT_ROOT)}")
    os.makedirs(output_dir, exist_ok=True)

    wandb_run = None
    wandb_module = None
    if config.get("wandb", {}).get("enabled", False):
        wandb_run = init_wandb_tracking(
            config,
            npc_key=config.get("npc_key", "unknown"),
            technique=config.get("technique", "unknown"),
            preset_name=preset_name,
            run_id=config.get("run_id", "unknown"),
            output_dir=output_dir,
            project=config.get("wandb", {}).get("project"),
            entity=config.get("wandb", {}).get("entity"),
        )
        if wandb_run is not None:
            wandb_module = sys.modules.get("wandb")

    # Report targets
    report_targets = []
    if config.get("logging", {}).get("enable_tensorboard", True):
        report_targets.append("tensorboard")
    if config.get("wandb", {}).get("enabled", False):
        report_targets.append("wandb")
    report_to = report_targets if report_targets else "none"

    args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=training.get("num_epochs", 3),
        max_steps=training.get("max_steps", -1) if training.get("max_steps", -1) > 0 else -1,
        per_device_train_batch_size=training.get("batch_size", 1),
        gradient_accumulation_steps=training.get("gradient_accumulation_steps", 8),
        warmup_steps=training.get("warmup_steps", 10),
        learning_rate=float(training.get("learning_rate", 2e-4)),
        lr_scheduler_type=training.get("lr_scheduler_type", "cosine"),
        weight_decay=training.get("weight_decay", 0.01),
        neftune_noise_alpha=training.get("neftune_noise_alpha", None),
        logging_steps=10,
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
        dataset_text_field=training.get("dataset_text_field", "text"),
        dataset_num_proc=training.get("dataset_num_proc", 0),
        max_length=training.get("max_seq_length", 2048),
        packing=training.get("packing", True),
    )

    if torch.cuda.is_available():
        model = model.to("cuda")

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        eval_dataset=eval_dataset,
        args=args,
    )

    # Apply train_on_responses_only to mask user tokens in loss when available.
    # Uses unsloth's train_on_responses_only (standalone function, not a trainer method).
    if training.get("train_on_responses_only", False) and hasattr(tokenizer, "apply_chat_template"):
        try:
            from unsloth import train_on_responses_only as _unsloth_response_only
        except ImportError:
            _unsloth_response_only = None
            print("  [WARN] unsloth.train_on_responses_only not available; continuing without response-only masking")

        if _unsloth_response_only is not None:
            # Detect instruction/response markers from the model's chat template.
            response_part = None
            instruction_part = None
            chat_template = tokenizer.chat_template or ""

            if "<|im_start|>" in chat_template:
                # ChatML format: Qwen, Phi, Mistral, etc.
                instruction_part = "<|im_start|>user"
                response_part = "<|im_start|>assistant"
            elif "<|start_header_id|>" in chat_template:
                # Llama 3 / Llama 3.1 / Llama 3.2 format
                instruction_part = "<|start_header_id|>user<|end_header_id|>"
                response_part = "<|start_header_id|>assistant<|end_header_id|>"
            else:
                # Try rendering one example to detect tokens
                try:
                    example = tokenizer.apply_chat_template(
                        [
                            {"role": "user", "content": "x"},
                            {"role": "assistant", "content": "y"},
                        ],
                        tokenize=False,
                    )
                    if "<|im_start|>assistant" in example:
                        instruction_part = "<|im_start|>user"
                        response_part = "<|im_start|>assistant"
                    elif "<|start_header_id|>assistant<|end_header_id|>" in example:
                        instruction_part = "<|start_header_id|>user<|end_header_id|>"
                        response_part = "<|start_header_id|>assistant<|end_header_id|>"
                except Exception as e:
                    pass

            if response_part is not None and instruction_part is not None:
                print(f"  [INFO] Applying train_on_responses_only (response marker: {response_part!r})")
                try:
                    _unsloth_response_only(
                        trainer,
                        instruction_part=instruction_part,
                        response_part=response_part,
                        tokenizer=tokenizer,
                    )
                except Exception as e:
                    print(f"  [WARN] train_on_responses_only failed: {e}; continuing without response-only masking")
            else:
                print("  [WARN] train_on_responses_only requested, but could not detect chat template format; continuing without response-only masking")

    print(f"  Starting training ({training.get('num_epochs', 3)} epochs, {training.get('batch_size', 1)} batch)...")
    try:
        train_result = trainer.train()

        # Save the final model
        print("  Saving model...")
        trainer.save_model(output_dir)
        tokenizer.save_pretrained(output_dir)

        # Save training metrics
        metrics = {}
        if train_result:
            metrics = train_result.metrics
        wandb_url = None
        if wandb_run is not None:
            wandb_url = getattr(wandb_run, "url", None) or getattr(getattr(wandb_module, "run", None), "url", None)
            if wandb_url:
                print(f"  [wandb] Logged run: {wandb_url}")
                if wandb_module is not None and getattr(wandb_module, "run", None) is not None:
                    try:
                        final_loss = metrics.get("train_loss", 0.0)
                        num_examples = len(dataset)
                        wandb_module.run.summary["train/wandb_url"] = wandb_url
                        wandb_module.run.summary["train/output_dir"] = output_dir
                        wandb_module.run.summary["train/final_loss"] = final_loss
                        wandb_module.run.summary["train/num_examples"] = num_examples
                        try:
                            wandb_module.log(
                                {
                                    "train/final_loss": final_loss,
                                    "train/num_examples": num_examples,
                                }
                            )
                        except Exception as e:
                            pass
                    except Exception as e:
                        pass
        metrics["wandb_url"] = wandb_url
        with open(os.path.join(output_dir, "training_metrics.json"), "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        # ── W&B Artifact Logging ──────────────────────────────────────────────
        if wandb_module is not None and getattr(wandb_module, "run", None) is not None:
            try:
                # Dataset artifact
                dataset_path = config.get("dataset_path", "")
                if os.path.isfile(dataset_path):
                    dataset_artifact = wandb_module.Artifact(
                        f"dataset-{config.get('npc_key', 'unknown')}",
                        type="dataset",
                        description=f"Training dataset for {config.get('npc_key', 'unknown')}: {config.get('technique', 'unknown')}, {len(dataset)} examples",
                        metadata={
                            "npc_key": config.get("npc_key", "unknown"),
                            "technique": config.get("technique", "unknown"),
                            "num_examples": len(dataset),
                            "dataset_sha256": file_sha256(dataset_path),
                        }
                    )
                    dataset_artifact.add_file(dataset_path)
                    wandb_module.log_artifact(dataset_artifact)
                elif os.path.isdir(dataset_path):
                    dataset_artifact = wandb_module.Artifact(
                        f"dataset-{config.get('npc_key', 'unknown')}",
                        type="dataset",
                        description=f"Training dataset for {config.get('npc_key', 'unknown')}: {config.get('technique', 'unknown')}, {len(dataset)} examples",
                        metadata={
                            "npc_key": config.get("npc_key", "unknown"),
                            "technique": config.get("technique", "unknown"),
                            "num_examples": len(dataset),
                        }
                    )
                    dataset_artifact.add_dir(dataset_path)
                    wandb_module.log_artifact(dataset_artifact)
            except Exception as e:
                pass

            try:
                # Config snapshot artifact
                snapshot_path = os.path.join(output_dir, "config_snapshot.yaml")
                if os.path.isfile(snapshot_path):
                    cfg_artifact = wandb_module.Artifact(
                        f"config-{config.get('npc_key', 'unknown')}",
                        type="config",
                        description=f"Training config snapshot for {config.get('npc_key', 'unknown')}",
                        metadata={
                            "npc_key": config.get("npc_key", "unknown"),
                            "preset": preset_name,
                            "run_id": config.get("run_id"),
                        }
                    )
                    cfg_artifact.add_file(snapshot_path)
                    wandb_module.log_artifact(cfg_artifact)
            except Exception as e:
                pass

            try:
                # LoRA adapter artifact
                if os.path.exists(output_dir):
                    final_loss_val = metrics.get("train_loss", 0.0)
                    lora_artifact = wandb_module.Artifact(
                        f"lora-{config.get('npc_key', 'unknown')}",
                        type="model",
                        description=f"LoRA adapter for {config.get('npc_key', 'unknown')}",
                        metadata={
                            "npc_key": config.get("npc_key", "unknown"),
                            "technique": config.get("technique", "unknown"),
                            "preset": preset_name,
                            "run_id": config.get("run_id"),
                            "final_loss": final_loss_val,
                            "num_examples": len(dataset),
                            "dataset_path": config.get("dataset_path"),
                        }
                    )
                    lora_artifact.add_dir(output_dir)
                    wandb_module.log_artifact(lora_artifact)
            except Exception as e:
                pass

        return trainer, metrics
    finally:
        if wandb_module is not None:
            try:
                wandb_module.finish()
            except Exception as e:
                pass


def main():
    parser = argparse.ArgumentParser(description="Unsloth training launcher")
    # Mode
    parser.add_argument("config_or_spec", nargs="?",
                        help="Path to YAML config or subject spec (with --from-spec)")
    parser.add_argument("--from-spec", action="store_true",
                        help="Interpret config_or_spec as a subject spec JSON")
    parser.add_argument("--technique", choices=["docs", "ollama", "template", "openai", "anthropic"],
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
    parser.add_argument("--wandb-project", default=None,
                        help="W&B project name (default: unsloth-core)")
    parser.add_argument("--wandb-entity", default=None,
                        help="W&B entity name (default: auto-detect)")
    parser.add_argument("--workflow-hooks", default=None,
                        help="Path to a JSONL hook log for step tracing (default: <output-dir>/workflow_hooks.jsonl)")
    parser.add_argument("--allow-ungated-dataset", action="store_true",
                        help="Allow training without a fresh passing dataset-eval artifact")

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

    spec_path = Path(config_path)
    if not (args.from_spec or spec_path.suffix.lower() == ".json"):
        spec_path = None
    elif not spec_path.exists():
        spec_path = None

    resolved_preset = config.get("preset") or args.preset or "default"
    preflight = run_preflight(
        phase="train",
        preset=resolved_preset,
        spec_path=spec_path,
        technique=args.technique or config.get("technique") or "template",
    )
    if preflight.errors:
        for message in preflight.errors:
            log_error("Preflight error: %s", message)
        sys.exit(1)
    if preflight.preset_effective and preflight.preset_effective != resolved_preset:
        log_warn(
            "Preflight downgraded preset from %s to %s for this GPU.",
            resolved_preset,
            preflight.preset_effective,
        )
        args.preset = preflight.preset_effective
        if args.from_spec:
            config = get_config_from_spec(config_path, preset=args.preset, overrides=cli_overrides)
        else:
            config = load_config(config_path, preset=args.preset, overrides=cli_overrides)

    if args.technique:
        config["technique"] = args.technique
        npc_for_path = config.get("npc_key", Path(config_path).stem)
        clean_path = paths.dataset_dir(npc_for_path) / args.technique / "train_clean.jsonl"
        raw_path = paths.dataset_dir(npc_for_path) / args.technique / "train.jsonl"
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

    # Set W&B project/entity from CLI if provided
    if getattr(args, "wandb_project", None):
        config.setdefault("wandb", {})["project"] = args.wandb_project
    if getattr(args, "wandb_entity", None):
        config.setdefault("wandb", {})["entity"] = args.wandb_entity

    ensure_wandb_noninteractive(config)

    # Forward WANDB_RUN_GROUP to HF Trainer so training runs are grouped
    # with the pipeline's eval runs in the W&B UI.
    wandb_group = os.environ.get("WANDB_GROUP")
    if wandb_group and config.get("wandb", {}).get("enabled"):
        os.environ["WANDB_RUN_GROUP"] = wandb_group

    # Print config summary
    npc_key = config.get("npc_key", "unknown")
    model_name = config.get("model", "unknown")
    technique = config.get("technique", "unknown")
    preset_name = config.get("preset") or args.preset or "default"
    lora_r = config.get("lora", {}).get("r", config.get("training", {}).get("lora_r", "?"))
    lora_alpha_val = config.get("lora", {}).get("alpha", config.get("training", {}).get("lora_alpha", "?"))
    vram_gb, vram_notes = estimate_vram(config)
    hook_recorder = WorkflowHookRecorder(
        args.workflow_hooks or default_hook_path(Path(config.get("output_dir") or paths.output_dir(npc_key))),
        tool="train",
        npc_key=npc_key,
        technique=technique,
        spec_path=str(config_path) if args.from_spec else None,
    )

    print()
    print("=" * 60)
    print("  Unsloth Training Launcher")
    print("=" * 60)
    print(f"  NPC:            {npc_key}")
    print(f"  Model:          {model_name}")
    print(f"  Technique:      {technique}")
    print(f"  LoRA Rank:      {lora_r}")
    print(f"  LoRA Alpha:     {lora_alpha_val}")
    print(f"  LR Scheduler:   {config.get('training', {}).get('lr_scheduler_type', 'cosine')}")
    print(f"  Estimated VRAM: {vram_gb}GB ({vram_notes})")
    print(f"  Preset:         {preset_name}")
    print(f"  W&B:            {'enabled' if config.get('wandb', {}).get('enabled') else 'disabled'}")
    print(f"  Export GGUF:    {'yes' if args.export_gguf else 'no'}")
    print("=" * 60)
    print()

    # ── Resolve output paths ───────────────────────────────────────────
    output_dir = config.get("output_dir")
    if output_dir:
        run_dir, run_id = get_run_output_path(output_dir, preset_name=preset_name, model_name=model_name)
    else:
        run_dir, run_id = get_run_output_path(str(paths.output_dir(npc_key)), preset_name=preset_name, model_name=model_name)

    config.setdefault("training", {})["output_dir"] = run_dir
    config["run_id"] = run_id
    config["preset"] = preset_name
    dataset_path = resolve_dataset_path(config, npc_key)

    if args.from_spec and args.allow_ungated_dataset:
        log_warn("Training without verifying a fresh dataset-eval artifact for %s", dataset_path)
    elif args.from_spec:
        quality_errors = dataset_quality_gate_errors(dataset_path)
        if quality_errors:
            log_error("Dataset quality gate is not ready for training:")
            for error in quality_errors:
                log_error("  - %s", error)
            log_error(
                "Run sanitize and dataset-eval again, or pass --allow-ungated-dataset for an intentional bypass."
            )
            sys.exit(1)
        log_info("Dataset quality gate verified for: %s", dataset_path)

    # Write config snapshot
    log_config_snapshot(config, run_dir)
    log_state("training_start", npc_key=npc_key, run_id=run_id, model=model_name, preset=preset_name)
    training_loss = None  # initialize early so it always exists in manifest scope

    # ── VRAM pre-flight check ───────────────────────────────────────────────
    free_vram_gb, total_vram_gb = query_gpu_memory()
    if free_vram_gb is not None:
        threshold = 1.25 * vram_gb
        if free_vram_gb < threshold:
            log_warn(
                "VRAM check: %.1fGB free / %.1fGB total — estimated need: %.1fGB (threshold: %.1fGB). "
                "Training may OOM. Consider a smaller preset, model, or lowering max_seq_length.",
                free_vram_gb, total_vram_gb or 0.0, vram_gb, threshold,
            )
        else:
            log_info(
                "VRAM check: %.1fGB free / %.1fGB total — estimated need: %.1fGB ✓",
                free_vram_gb, total_vram_gb or 0.0, vram_gb,
            )
    else:
        log_warn("VRAM check: could not query GPU memory (nvidia-smi not available)")

    with hook_recorder.step("training_pipeline", run_id=run_id, output_dir=run_dir, export_gguf=bool(args.export_gguf), preset=preset_name):

        # ── Load model ─────────────────────────────────────────────────────
        log_info("[1/4] Loading model and tokenizer...")
        with hook_recorder.step("load_model", model=model_name, preset=preset_name):
            model, tokenizer = get_model_and_tokenizer(config)
        log_info("Model loaded")

        # ── Load dataset ───────────────────────────────────────────────────
        log_info("[2/4] Loading dataset...")
        with hook_recorder.step("load_dataset", dataset_path=dataset_path):
            dataset = load_dataset_from_jsonl(dataset_path, tokenizer, config, label="training")
            eval_dataset = None
            validation_path = validation_dataset_path(dataset_path)
            if validation_path:
                eval_dataset = load_dataset_from_jsonl(validation_path, tokenizer, config, label="validation")
                log_info("Validation dataset loaded from: %s", validation_path)
            num_examples = len(dataset)
        log_info("Dataset loaded: %d examples", num_examples)

        # ── Training ───────────────────────────────────────────────────────
        log_info("[3/4] Running training...")
        with hook_recorder.step("run_training", dataset_path=dataset_path, num_examples=num_examples):
            trainer, metrics = run_training(model, tokenizer, dataset, eval_dataset, config, preset_name=preset_name)
        training_loss = metrics.get("train_loss", 0.0)
        wandb_url = metrics.get("wandb_url")
        if wandb_url:
            log_info("W&B run: %s", wandb_url)
        log_info("Training complete: loss=%.4f", training_loss)
        log_state("training_complete", npc_key=npc_key, run_id=run_id, loss=training_loss, examples=num_examples)

        # ── Promotion check ────────────────────────────────────────────────
        with hook_recorder.step("promotion_check", training_loss=training_loss, num_examples=num_examples):
            promotion_passed, promotion_failures = check_promotion_rules(
                training_loss, config, num_examples
            )
        run_pointer_target = Path("runs") / run_id
        if promotion_passed:
            log_info("Promotion rules passed")
            # Create/update 'best' symlink to this run
            best_link = Path(output_dir or paths.output_dir(npc_key)) / "best"
            update_run_pointer(best_link, run_pointer_target, "best")
        else:
            log_warn("Promotion rules failed:")
            for failure in promotion_failures:
                log_warn("  - %s", failure)

        # Always update 'latest' symlink regardless of promotion result
        latest_link = Path(output_dir or paths.output_dir(npc_key)) / "latest"
        update_run_pointer(latest_link, run_pointer_target, "latest")

        # ── GGUF Export ────────────────────────────────────────────────────

        if args.export_gguf:
            log_info("[4/4] Exporting to GGUF (adapter mode for Unity)...")
            exports_dir = paths.export_dir(npc_key)
            exports_dir.mkdir(parents=True, exist_ok=True)

            # Use the unified export.py in adapter mode (fast, no base model loading)
            export_script = PROJECT_ROOT / "scripts" / "export" / "export.py"
            export_cmd = [sys.executable, str(export_script), str(output_dir)]
            if getattr(args, 'full_merge_export', False):
                export_cmd.append("--full-merge")
                quant = args.quantization or config.get("export", {}).get("quantization", "q4_k_m")
                export_cmd.extend(["--quantization", quant])
                log_info("  Mode: full-merge (standalone GGUF)")
            else:
                log_info("  Mode: adapter-only (LLMUnity compatible)")

            log_info("  Running: %s", " ".join(str(c) for c in export_cmd[2:]))
            result = subprocess.run(export_cmd, capture_output=False, text=True, timeout=7200)
            if result.returncode != 0:
                log_error("GGUF export failed (exit %d)", result.returncode)
            else:
                log_info("GGUF export complete")

            # Write manifest with export info
            gguf_files = sorted(exports_dir.glob(f"{npc_key}*.gguf"))
            manifest = {
                "npc_key": npc_key,
                "run_id": run_id,
                "base_model": config.get("model"),
                "technique": technique,
                "training_loss": training_loss,
                "num_examples": num_examples,
                "wandb_url": wandb_url,
                "created_at": datetime.now().isoformat(),
                "mode": "full_merge" if getattr(args, 'full_merge_export', False) else "adapter",
                "gguf_files": [str(gf) for gf in gguf_files],
            }
            manifest_path = exports_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            log_info("  Manifest: %s", manifest_path)

            # ── W&B GGUF Artifact ────────────────────────────────────────────────
            if config.get("wandb", {}).get("enabled", False) and gguf_files:
                try:
                    import wandb as _wandb
                    export_run = _wandb.init(
                        project=config.get("wandb", {}).get("project", "unsloth-core"),
                        entity=config.get("wandb", {}).get("entity"),
                        group=os.environ.get("WANDB_RUN_GROUP") or os.environ.get("WANDB_GROUP") or npc_key,
                        job_type="export",
                        name=f"export-{npc_key}-{run_id}",
                        tags=["export", npc_key, technique, preset_name],
                        config={
                            "npc_key": npc_key,
                            "technique": technique,
                            "preset": preset_name,
                            "run_id": run_id,
                            "training_wandb_url": wandb_url,
                            "training_loss": training_loss,
                            "num_examples": num_examples,
                            "mode": "full_merge" if getattr(args, 'full_merge_export', False) else "adapter",
                            "gguf_files": [str(gf) for gf in gguf_files],
                        },
                    )
                    gguf_artifact = _wandb.Artifact(
                        f"gguf-{npc_key}",
                        type="gguf-export",
                        description=f"GGUF export for {npc_key}: {len(gguf_files)} file(s)",
                        metadata={
                            "npc_key": npc_key,
                            "technique": technique,
                            "preset": preset_name,
                            "training_loss": training_loss,
                            "num_examples": num_examples,
                            "mode": "full_merge" if getattr(args, 'full_merge_export', False) else "adapter",
                            "run_id": run_id,
                            "training_wandb_url": wandb_url,
                            "wandb_url": getattr(export_run, "url", None),
                        }
                    )
                    for gf in gguf_files:
                        gguf_artifact.add_file(str(gf))
                    _wandb.log_artifact(gguf_artifact)
                    _wandb.finish()
                    log_info("  [wandb] Logged GGUF artifact")
                except Exception as exc:
                    log_warn("  [wandb] GGUF artifact logging failed: %s", exc)
        else:
            log_info("[4/4] Skipping GGUF export (use --export-gguf to enable)")

    log_state("training_finished", npc_key=npc_key, run_id=run_id, loss=training_loss,
              export=bool(args.export_gguf), promoted=promotion_passed)
    print(f"\n{'='*60}")
    print(f"  Training complete!")
    print(f"  Run ID:  {run_id}")
    print(f"  Output:  {run_dir}")
    if args.export_gguf:
        exports_dir = paths.export_dir(npc_key)
        print(f"  Exports: {exports_dir}")
    print(f"{'='*60}\n")

    # ── Record pipeline manifest stage ─────────────────────────────────
    try:
        from scripts.ops.pipeline_manifest import record_pipeline_stage
        os.environ.setdefault("NPC_KEY", npc_key)
        os.environ.setdefault("TECHNIQUE", technique)
        manifest_artifacts = {}
        if run_dir and os.path.exists(run_dir):
            manifest_artifacts["run_dir"] = str(run_dir)
        if config and config.get("output_dir"):
            manifest_artifacts["output_dir"] = config["output_dir"]
        manifest_metadata = {}
        if training_loss is not None:
            manifest_metadata["training_loss"] = training_loss
        record_pipeline_stage("train", artifacts=manifest_artifacts, metadata=manifest_metadata)
        from scripts.ops.artifact_registry import record_stage_artifacts_best_effort
        record_stage_artifacts_best_effort(
            run_id,
            npc_key,
            "train",
            manifest_artifacts,
            technique=technique,
            metadata=manifest_metadata,
        )
    except Exception:
        pass  # manifest is optional, never block pipeline


if __name__ == "__main__":
    main()
