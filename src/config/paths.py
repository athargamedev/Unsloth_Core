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
  - Dataset dir:   subjects/datasets/{npc_key}/{technique}/
  - Eval reports:  eval/reports/{npc_key}/
"""

import re

from datetime import date, datetime, timezone
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Handle both old and new directory structures for backward compatibility
_old_scripts_dir = PROJECT_ROOT / "scripts"
_old_config_dir = PROJECT_ROOT / "_config"
_new_scripts_dir = PROJECT_ROOT / "src" / "core"
_new_config_dir = PROJECT_ROOT / "src" / "config"

# Prefer new paths, fall back to old (via symlinks)
SCRIPTS_DIR = _new_scripts_dir if _new_scripts_dir.exists() else _old_scripts_dir
CONFIG_DIR = _new_config_dir if _new_config_dir.exists() else _old_config_dir


# ── Pipeline registry (unified run/log source of truth) ──────────────────────

def pipeline_root() -> Path:
    """Return var/.pipeline/ or .pipeline/ — unified runtime registry root."""
    new_path = PROJECT_ROOT / "var" / ".pipeline"
    return new_path if new_path.exists() else PROJECT_ROOT / ".pipeline"


def pipeline_index_path() -> Path:
    """Return .pipeline/runs.jsonl — append-only pipeline index."""
    return pipeline_root() / "runs.jsonl"


def pipeline_runs_root() -> Path:
    """Return .pipeline/runs/ — per-run directories."""
    return pipeline_root() / "runs"


def pipeline_run_dir(run_id: str) -> Path:
    """Return .pipeline/runs/{run_id}/."""
    return pipeline_runs_root() / run_id


def pipeline_hook_path(run_id: str) -> Path:
    """Return the workflow hook log for a pipeline run."""
    return pipeline_run_dir(run_id) / "workflow_hooks.jsonl"


def pipeline_log_state_path(run_id: str) -> Path:
    """Return the structured log_state JSONL for a pipeline run."""
    return pipeline_run_dir(run_id) / "log_state.jsonl"


# ── Shared validation constants ──────────────────────────────────────────────

SNAKE_CASE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


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

DATASET_TECHNIQUES = ("docs", "ollama", "openai", "anthropic", "template")


def dataset_root() -> Path:
    """Return data/datasets/ or subjects/datasets/."""
    new_path = PROJECT_ROOT / "data" / "datasets"
    return new_path if new_path.exists() else PROJECT_ROOT / "subjects" / "datasets"


def dataset_dir(npc_key: str) -> Path:
    """Return subjects/datasets/{npc_key}/"""
    return dataset_root() / npc_key


def dataset_train_path(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/train.jsonl"""
    return dataset_dir(npc_key) / technique / "train.jsonl"


def dataset_val_path(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/validation.jsonl"""
    return dataset_dir(npc_key) / technique / "validation.jsonl"


def dataset_reference_dir(npc_key: str, technique: str = "template") -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/reference_doc/"""
    return dataset_dir(npc_key) / technique / "reference_doc"


def dataset_manifest_path(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/manifests/dataset_manifest.json."""
    return dataset_dir(npc_key) / technique / "manifests" / "dataset_manifest.json"


def generation_config_path(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/generation_config.json."""
    return dataset_dir(npc_key) / technique / "generation_config.json"


def dataset_log_dir(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/logs/."""
    return dataset_dir(npc_key) / technique / "logs"


def dataset_raw_dir(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/raw/."""
    return dataset_dir(npc_key) / technique / "raw"


def dataset_clean_dir(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/clean/."""
    return dataset_dir(npc_key) / technique / "clean"


def dataset_eval_dir(npc_key: str, technique: str) -> Path:
    """Return subjects/datasets/{npc_key}/{technique}/eval/."""
    return dataset_dir(npc_key) / technique / "eval"


def autodetect_dataset(npc_key: str) -> tuple[str, Path, Path] | None:
    """Auto-detect the best available dataset technique for an NPC.

    Returns (technique, train_path, val_path) or None if none found.
    Preference order: docs > ollama > API-generated > template.
    """
    for technique in DATASET_TECHNIQUES:
        train = dataset_train_path(npc_key, technique)
        val = dataset_val_path(npc_key, technique)
        if train.exists() and val.exists():
            return technique, train, val
        # Allow missing validation file for backward compat
        if train.exists():
            return technique, train, val
    return None


def resolve_dataset_context(npc_key: str, preferred_technique: str | None = None) -> tuple[str, Path, Path]:
    """Resolve the dataset technique and canonical train/val files for an NPC.

    If a preferred technique is provided, that dataset wins even when it does
    not exist yet so generation commands can create the requested technique.
    Otherwise we fall back to the best available technique on disk. If nothing exists
    yet, we return canonical paths for the preferred technique or template.
    """
    preferred = (preferred_technique or "").strip()
    if preferred in DATASET_TECHNIQUES:
        train = dataset_train_path(npc_key, preferred)
        clean = train.with_name("train_clean.jsonl")
        if clean.exists():
            return preferred, clean, dataset_val_path(npc_key, preferred)
        return preferred, train, dataset_val_path(npc_key, preferred)

    detected = autodetect_dataset(npc_key)
    if detected:
        technique, train, val = detected
        clean = train.with_name("train_clean.jsonl")
        if clean.exists():
            return technique, clean, val
        return technique, train, val

    technique = preferred if preferred in DATASET_TECHNIQUES else "template"
    train = dataset_train_path(npc_key, technique)
    clean = train.with_name("train_clean.jsonl")
    if clean.exists():
        train = clean
    return technique, train, dataset_val_path(npc_key, technique)


def is_canonical_train_path(path: str | Path) -> bool:
    """Return True if path matches subjects/datasets/{npc_key}/{technique}/train.jsonl."""
    p = Path(path)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()
    try:
        rel = p.relative_to(dataset_root().resolve())
    except Exception:
        return False
    parts = rel.parts
    return len(parts) == 3 and parts[1] in DATASET_TECHNIQUES and parts[2] == "train.jsonl"


def infer_validation_path(train_path: str | Path) -> Path:
    """Infer validation path from a train path.

    Canonical path is subjects/datasets/{npc_key}/{technique}/train.jsonl -> validation.jsonl.
    For non-canonical paths, this returns a best-effort sibling filename.
    """
    p = Path(train_path)
    if not p.is_absolute():
        p = (PROJECT_ROOT / p).resolve()

    if is_canonical_train_path(p):
        return p.parent / "validation.jsonl"

    if p.suffix == ".jsonl":
        return p.with_name(f"{p.stem}_validation.jsonl")

    return p.parent / "validation.jsonl"


# ── Dataset versioning ───────────────────────────────────────────────────────

def dataset_version_dir(npc_key: str, technique: str, version: str) -> Path:
    """Return Path to versioned dataset dir: subjects/datasets/{npc}/{technique}/v{version}/"""
    return dataset_dir(npc_key) / technique / f"v{version}"


def dataset_latest_symlink(npc_key: str, technique: str) -> Path:
    """Return Path to latest symlink: subjects/datasets/{npc}/{technique}/latest"""
    return dataset_dir(npc_key) / technique / "latest"


def dataset_latest_actual_dir(npc_key: str, technique: str) -> Path | None:
    """Resolve 'latest' symlink to actual versioned dir. Returns None if no symlink."""
    link = dataset_latest_symlink(npc_key, technique)
    if link.is_symlink() and link.exists():
        return link.resolve()
    return None


def dataset_latest_train_path(npc_key: str, technique: str) -> Path | None:
    """Resolve latest train.jsonl, preferring train_clean.jsonl if available."""
    actual = dataset_latest_actual_dir(npc_key, technique)
    if actual is not None:
        clean = actual / "train_clean.jsonl"
        if clean.exists():
            return clean
        raw = actual / "train.jsonl"
        if raw.exists():
            return raw
    return None


def generate_version_timestamp() -> str:
    """Generate version string: YYYYMMDD_HHMMSS"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# ── Subjects (NPC spec files) ────────────────────────────────────────────────

def subjects_root() -> Path:
    """Return data/npcs/ or subjects/ directory root."""
    new_path = PROJECT_ROOT / "data" / "npcs"
    return new_path if new_path.exists() else PROJECT_ROOT / "subjects"


def spec_dir() -> Path:
    """Return data/npcs/specs/ or subjects/NPC_specs/."""
    new_path = PROJECT_ROOT / "data" / "npcs" / "specs"
    return new_path if new_path.exists() else subjects_root() / "NPC_specs"


def spec_path(npc_key: str) -> Path:
    """Return subjects/NPC_specs/{npc_key}.json."""
    return spec_dir() / f"{npc_key}.json"


# ── Per-NPC workflow config ───────────────────────────────────────────────────

def npc_config_root() -> Path:
    """Return etc/npcs/ or configs/npcs/."""
    new_path = PROJECT_ROOT / "etc" / "npcs"
    return new_path if new_path.exists() else PROJECT_ROOT / "configs" / "npcs"


def npc_config_dir(npc_key: str) -> Path:
    """Return configs/npcs/{npc_key}/."""
    return npc_config_root() / npc_key


def npc_workflow_config_path(npc_key: str) -> Path:
    """Return configs/npcs/{npc_key}/workflow.yaml."""
    return npc_config_dir(npc_key) / "workflow.yaml"


def training_config_path(npc_key: str) -> Path:
    """Return configs/npcs/{npc_key}/training.yaml."""
    return npc_config_dir(npc_key) / "training.yaml"


def evaluation_config_path(npc_key: str) -> Path:
    """Return configs/npcs/{npc_key}/evaluation.yaml."""
    return npc_config_dir(npc_key) / "evaluation.yaml"


def npc_generation_config_path(npc_key: str) -> Path:
    """Return configs/npcs/{npc_key}/generation.yaml."""
    return npc_config_dir(npc_key) / "generation.yaml"


def sweep_dir(npc_key: str) -> Path:
    """Return configs/npcs/{npc_key}/sweeps/."""
    return npc_config_dir(npc_key) / "sweeps"


# ── Logs and per-NPC pipeline registry ────────────────────────────────────────

def log_root() -> Path:
    """Return artifacts/logs/ or logs/."""
    new_path = PROJECT_ROOT / "artifacts" / "logs"
    return new_path if new_path.exists() else PROJECT_ROOT / "logs"


def npc_log_root(npc_key: str) -> Path:
    """Return logs/{npc_key}/."""
    return log_root() / npc_key


def npc_log_dir(npc_key: str, stage: str) -> Path:
    """Return logs/{npc_key}/{stage}/."""
    return npc_log_root(npc_key) / stage


def pipeline_npcs_root() -> Path:
    """Return .pipeline/npcs/."""
    return pipeline_root() / "npcs"


def npc_pipeline_root(npc_key: str) -> Path:
    """Return .pipeline/npcs/{npc_key}/."""
    return pipeline_npcs_root() / npc_key


def npc_pipeline_index_path(npc_key: str) -> Path:
    """Return .pipeline/npcs/{npc_key}/index.json."""
    return npc_pipeline_root(npc_key) / "index.json"


def npc_pipeline_runs_path(npc_key: str) -> Path:
    """Return .pipeline/npcs/{npc_key}/runs.jsonl."""
    return npc_pipeline_root(npc_key) / "runs.jsonl"


# ── Outputs (LoRA adapters + checkpoints, NO GGUF) ──────────────────────────

def output_root() -> Path:
    """Return artifacts/models/ or outputs/."""
    new_path = PROJECT_ROOT / "artifacts" / "models"
    return new_path if new_path.exists() else PROJECT_ROOT / "outputs"


def output_dir(npc_key: str) -> Path:
    """Return outputs/{npc_key}/"""
    return output_root() / npc_key


# ── Exports (GGUF only — deployable artifacts) ──────────────────────────────

def export_root() -> Path:
    """Return artifacts/exports/ or exports/."""
    new_path = PROJECT_ROOT / "artifacts" / "exports"
    return new_path if new_path.exists() else PROJECT_ROOT / "exports"


def export_dir(npc_key: str) -> Path:
    """Return exports/{npc_key}/"""
    return export_root() / npc_key


def export_adapter_dir(npc_key: str) -> Path:
    """Return exports/{npc_key}/adapters/."""
    return export_dir(npc_key) / "adapters"


def export_unity_dir(npc_key: str) -> Path:
    """Return exports/{npc_key}/unity/."""
    return export_dir(npc_key) / "unity"


def export_unity_alias_path(npc_key: str, outtype: str = "f16") -> Path:
    """Return exports/{npc_key}/unity/{npc_key}-lora-{outtype}.gguf."""
    return export_unity_dir(npc_key) / f"{npc_key}-lora-{outtype}.gguf"


def npc_workflow_manifest_path(npc_key: str) -> Path:
    """Return outputs/{npc_key}/workflow_manifest.json."""
    return output_dir(npc_key) / "workflow_manifest.json"


def export_gguf_path(npc_key: str, model_id: str, quant: str = "q4_k_m") -> Path:
    """Return exports/{npc_key}/{npc_key}-{model_short}-{quant}.gguf"""
    short = model_short_name(model_id)
    return export_dir(npc_key) / f"{npc_key}-{short}-{quant}.gguf"


def export_manifest_path(npc_key: str) -> Path:
    """Return exports/{npc_key}/manifest.json"""
    return export_dir(npc_key) / "manifest.json"


# ── Evaluation ───────────────────────────────────────────────────────────────

def eval_root() -> Path:
    """Return artifacts/eval/ or eval/."""
    new_path = PROJECT_ROOT / "artifacts" / "eval"
    return new_path if new_path.exists() else PROJECT_ROOT / "eval"


def eval_training_metrics_path(npc_key: str) -> Path:
    """Return eval/training-metrics/{npc_key}.yaml"""
    return eval_root() / "training-metrics" / f"{npc_key}.yaml"


def eval_report_dir(npc_key: str) -> Path:
    """Return eval/reports/{npc_key}/"""
    return eval_root() / "reports" / npc_key


def eval_feedback_path(npc_key: str) -> Path:
    """Return eval/results/feedback/{npc_key}.json"""
    return eval_root() / "results" / "feedback" / f"{npc_key}.json"

def eval_gaps_dir(npc_key: str) -> Path:
    """Return eval/results/gaps/{npc_key}/"""
    return eval_root() / "results" / "gaps" / npc_key



def eval_timestamp() -> str:
    """Return a UTC timestamp suitable for eval report filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


def eval_report_path(npc_key: str, fmt: str = "md", timestamp: str | None = None) -> Path:
    """Return eval/reports/{npc_key}/eval_{timestamp}.{fmt}"""
    ts = timestamp or eval_timestamp()
    return eval_report_dir(npc_key) / f"eval_{ts}.{fmt}"


def eval_comparison_dir() -> Path:
    """Return eval/comparisons/"""
    return eval_root() / "comparisons"


def eval_comparison_path(npc_key: str, baseline_label: str, timestamp: str | None = None) -> Path:
    """Return eval/comparisons/{npc_key}_vs_{baseline}_{timestamp}.md"""
    ts = timestamp or eval_timestamp()
    return eval_comparison_dir() / f"{npc_key}_vs_{baseline_label}_{ts}.md"


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
        eval_root() / "results" / "feedback",
        eval_root() / "results" / "gaps",
        npc_config_root(),
        log_root(),
        pipeline_root(),
        pipeline_runs_root(),
        pipeline_npcs_root(),
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


def best_run_dir(npc_key: str) -> Path | None:
    """Resolve the 'best' symlink (lowest training loss) for an NPC."""
    link = output_dir(npc_key) / "best"
    if link.exists() and link.is_symlink():
        target = link.resolve()
        if target.exists():
            return target
    if link.exists() and link.is_dir():
        return link
    return None


def _has_adapter_config(adapter_dir: Path) -> bool:
    """Return True when a directory contains a PEFT adapter config."""
    return (adapter_dir / "adapter_config.json").exists()


def _newest_adapter_dir(candidates: list[Path]) -> Path | None:
    """Return the newest directory containing adapter files from candidates."""
    adapter_dirs = [path for path in candidates if path.is_dir() and _has_adapter_config(path)]
    if not adapter_dirs:
        return None

    return max(adapter_dirs, key=lambda path: path.stat().st_mtime)


def _latest_direct_adapter_run_dir(npc_key: str) -> Path | None:
    """Return the newest outputs/{npc_key}/run_* directory with adapter files."""
    npc_output_dir = output_dir(npc_key)
    if not npc_output_dir.exists():
        return None

    return _newest_adapter_dir([
        path
        for path in npc_output_dir.iterdir()
        if path.is_dir() and path.name.startswith("run_")
    ])


def _latest_nested_adapter_run_dir(npc_key: str) -> Path | None:
    """Return the newest outputs/{npc_key}/runs/* directory with adapter files."""
    runs_dir = output_dir(npc_key) / "runs"
    if not runs_dir.exists():
        return None

    return _newest_adapter_dir([path for path in runs_dir.iterdir() if path.is_dir()])


def _latest_adapter_run_dir(npc_key: str) -> Path | None:
    """Return the newest valid adapter across legacy and canonical run layouts."""
    candidates = []
    for adapter_dir in (_latest_direct_adapter_run_dir(npc_key), _latest_nested_adapter_run_dir(npc_key)):
        if adapter_dir is not None:
            candidates.append(adapter_dir)
    return _newest_adapter_dir(candidates)


def _resolve_npc_adapter_dir(npc_key: str) -> Path:
    """Resolve an NPC key to the highest-priority valid adapter directory."""
    npc_output_dir = output_dir(npc_key)
    fallback_order = [
        best_run_dir(npc_key),
        latest_run_dir(npc_key),
        _latest_adapter_run_dir(npc_key),
        npc_output_dir,
    ]

    for adapter_dir in fallback_order:
        if adapter_dir and _has_adapter_config(adapter_dir):
            return adapter_dir

    return npc_output_dir


def _infer_npc_key_from_adapter_path(candidate: Path, adapter_dir: Path) -> str:
    """Infer the NPC key while preserving outputs/<npc_key>/run_* semantics."""
    if candidate.name in {"best", "latest"} and candidate.parent.name:
        return candidate.parent.name

    if adapter_dir.parent.name == "runs":
        return adapter_dir.parent.parent.name

    if adapter_dir.name.startswith("run_") and adapter_dir.parent.parent == output_root():
        return adapter_dir.parent.name

    return adapter_dir.name


def resolve_adapter_dir(npc_key_or_dir: str | Path) -> tuple[str, Path]:
    """Resolve an NPC key, output dir, latest symlink, or run dir to an adapter dir.

    Returns (npc_key, adapter_dir). Raises FileNotFoundError with a setup-oriented
    message when no PEFT adapter is present.
    """
    candidate = Path(npc_key_or_dir)
    if not candidate.exists():
        # Not an existing path — treat as NPC key
        npc_key = str(npc_key_or_dir)
        adapter_dir = _resolve_npc_adapter_dir(npc_key)
    else:
        # Check name BEFORE following symlinks
        resolved_candidate = candidate.resolve()
        try:
            relative_to_outputs = resolved_candidate.relative_to(output_root().resolve())
        except ValueError:
            relative_to_outputs = None

        if relative_to_outputs is not None and len(relative_to_outputs.parts) == 1:
            npc_key = relative_to_outputs.parts[0]
            adapter_dir = _resolve_npc_adapter_dir(npc_key)
        else:
            adapter_dir = candidate
            if adapter_dir.name in {"best", "latest"}:
                adapter_dir = adapter_dir.resolve()
            elif adapter_dir.is_symlink() or adapter_dir.exists():
                adapter_dir = resolved_candidate
            npc_key = _infer_npc_key_from_adapter_path(candidate, adapter_dir)

    if _has_adapter_config(adapter_dir):
        return npc_key, adapter_dir

    raise FileNotFoundError(
        f"No PEFT adapter found at {adapter_dir}. Expected adapter_config.json. "
        f"Train first, or pass outputs/<npc_key>/best, outputs/<npc_key>/latest, "
        f"outputs/<npc_key>/run_<nnn>, or outputs/<npc_key>/runs/<run_id>."
    )
