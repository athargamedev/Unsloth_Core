#!/usr/bin/env python3
"""
_config/paths.py — Shared path helpers for Unsloth_Core.

Centralizes all path resolution so that scripts use consistent
naming and directory conventions. Import this instead of hardcoding paths.

Naming conventions:
  - GGUF filename: {npc_key}-{model_short}-{quant}.gguf
  - Model short:   unsloth/Llama-3.2-3B-Instruct-bnb-4bit → llama3.2-3b
  - Output dir:    outputs/{npc_key}/
  - Export dir:    exports/{npc_key}/
  - Dataset dir:   datasets/{npc_key}/{technique}/
  - Eval reports:  eval/reports/{npc_key}/
"""

import re

from datetime import date
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── Model short name derivation ──────────────────────────────────────────────

_MODEL_SUFFIXES = [
    "-Instruct-bnb-4bit",
    "-bnb-4bit",
    "-Instruct",
    "-GGUF",
]


def model_short_name(model_id: str) -> str:
    """Derive a short, readable model name from a HuggingFace model ID.

    Examples:
        unsloth/Llama-3.2-3B-Instruct-bnb-4bit  →  llama3.2-3b
        unsloth/Qwen3-1.7B-bnb-4bit              →  qwen3-1.7b
        unsloth/Llama-3.1-8B-Instruct-bnb-4bit   →  llama3.1-8b
    """
    name = model_id.split("/")[-1]  # Drop org prefix
    for suffix in _MODEL_SUFFIXES:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return re.sub(r"(?<=[a-zA-Z])-(?=\d)", "", name).lower()


# ── Datasets ─────────────────────────────────────────────────────────────────

DATASET_TECHNIQUES = ("template", "ollama", "notebooklm")


def dataset_root() -> Path:
    return PROJECT_ROOT / "datasets"


def dataset_dir(npc_key: str) -> Path:
    """Return datasets/{npc_key}/"""
    return dataset_root() / npc_key


def dataset_train_path(npc_key: str, technique: str = "notebooklm") -> Path:
    """Return datasets/{npc_key}/{technique}/train.jsonl"""
    return dataset_dir(npc_key) / technique / "train.jsonl"


def dataset_val_path(npc_key: str, technique: str = "notebooklm") -> Path:
    """Return datasets/{npc_key}/{technique}/validation.jsonl"""
    return dataset_dir(npc_key) / technique / "validation.jsonl"


def autodetect_dataset(npc_key: str) -> tuple[str, Path, Path] | None:
    """Auto-detect the best available dataset technique for an NPC.

    Returns (technique, train_path, val_path) or None if none found.
    Preference order: ollama > notebooklm > template.
    """
    for technique in ("ollama", "notebooklm", "template"):
        train = dataset_train_path(npc_key, technique)
        val = dataset_val_path(npc_key, technique)
        if train.exists() and val.exists():
            return technique, train, val
        # Allow missing validation file for backward compat
        if train.exists():
            return technique, train, val
    return None


# ── Outputs (LoRA adapters + checkpoints, NO GGUF) ──────────────────────────

def output_root() -> Path:
    return PROJECT_ROOT / "outputs"


def output_dir(npc_key: str) -> Path:
    """Return outputs/{npc_key}/"""
    return output_root() / npc_key


def output_colab_dir(npc_key: str) -> Path:
    """Return outputs/colab/{npc_key}/ for Colab-trained variants."""
    return output_root() / "colab" / npc_key


# ── Exports (GGUF only — deployable artifacts) ──────────────────────────────

def export_root() -> Path:
    return PROJECT_ROOT / "exports"


def export_dir(npc_key: str) -> Path:
    """Return exports/{npc_key}/"""
    return export_root() / npc_key


def export_gguf_path(npc_key: str, model_id: str, quant: str = "q4_k_m") -> Path:
    """Return exports/{npc_key}/{npc_key}-{model_short}-{quant}.gguf"""
    short = model_short_name(model_id)
    return export_dir(npc_key) / f"{npc_key}-{short}-{quant}.gguf"


def export_manifest_path(npc_key: str) -> Path:
    """Return exports/{npc_key}/manifest.json"""
    return export_dir(npc_key) / "manifest.json"


# ── Evaluation ───────────────────────────────────────────────────────────────

def eval_root() -> Path:
    return PROJECT_ROOT / "eval"


def eval_training_metrics_path(npc_key: str) -> Path:
    """Return eval/training-metrics/{npc_key}.yaml"""
    return eval_root() / "training-metrics" / f"{npc_key}.yaml"


def eval_report_dir(npc_key: str) -> Path:
    """Return eval/reports/{npc_key}/"""
    return eval_root() / "reports" / npc_key


def eval_report_path(npc_key: str, fmt: str = "md") -> Path:
    """Return eval/reports/{npc_key}/eval_{today}.{fmt}"""
    today = date.today().isoformat()
    return eval_report_dir(npc_key) / f"eval_{today}.{fmt}"


def eval_comparison_dir() -> Path:
    """Return eval/comparisons/"""
    return eval_root() / "comparisons"


def eval_comparison_path(npc_key: str, baseline_label: str) -> Path:
    """Return eval/comparisons/{npc_key}_vs_{baseline}_{today}.md"""
    today = date.today().isoformat()
    return eval_comparison_dir() / f"{npc_key}_vs_{baseline_label}_{today}.md"


def eval_results_path() -> Path:
    """Return eval/results/eval_results.jsonl"""
    return eval_root() / "results" / "eval_results.jsonl"


# ── Subdir initialisation ────────────────────────────────────────────────────

def ensure_dirs(*paths: Path) -> None:
    """Create parent directories for all given paths if they don't exist."""
    for p in paths:
        p.parent.mkdir(parents=True, exist_ok=True)


def ensure_all() -> None:
    """Create the full directory scaffold."""
    dirs = [
        dataset_root(),
        output_root(),
        export_root(),
        eval_root(),
        eval_root() / "training-metrics",
        eval_root() / "reports",
        eval_root() / "comparisons",
        eval_root() / "results",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# ── Run ID experiment tracking ──────────────────────────────────────────────


def generate_run_id(npc_key: str, preset_name: str = "default") -> str:
    """Generate a unique run ID: {YYYYMMDD}_{preset_name}_{sequential_number}

    Sequential numbering resets daily per NPC.
    """
    today = date.today().strftime("%Y%m%d")
    runs_dir = output_dir(npc_key) / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Count existing runs with today's date and same preset
    existing = list(runs_dir.glob(f"{today}_{preset_name}_*"))
    seq = len(existing) + 1
    return f"{today}_{preset_name}_{seq:03d}"


def run_dir(npc_key: str, run_id: str) -> Path:
    """Return outputs/{npc_key}/runs/{run_id}/"""
    return output_dir(npc_key) / "runs" / run_id


def latest_run_dir(npc_key: str) -> Path | None:
    """Resolve the 'latest' symlink for an NPC."""
    link = output_dir(npc_key) / "latest"
    if link.exists() and link.is_symlink():
        target = link.resolve()
        if target.exists():
            return target
    return None
