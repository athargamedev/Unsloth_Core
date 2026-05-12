"""
scripts/colab/__init__.py — Colab notebook generation engine.

Exports ``generate_colab_notebook`` for generating Unsloth-compatible
training notebooks from subject specs, and ``COLAB_PRESETS`` for
Colab T4-optimised training presets.
"""

from scripts.colab.presets import COLAB_PRESETS, get_colab_preset, list_colab_presets
from scripts.colab.dataset_packager import (
    upload_to_hub,
    dataset_to_inline_jsonl,
    estimate_dataset_size,
)
from scripts.colab.render import render_notebook

import os
import json
from pathlib import Path


def generate_colab_notebook(
    *,
    data_path: str,
    model_name: str = "unsloth/Llama-3.1-8B-Instruct-bnb-4bit",
    preset_name: str = "fast-8b",
    subject_spec: dict | None = None,
    hf_repo_id: str | None = None,
    output_dir: str | None = None,
    huggingface_token: str | None = None,
    data_mode: str | None = None,
    drive_data_path: str | None = None,
    drive_gguf_dir: str | None = None,
) -> str:
    """Generate an Unsloth-compatible Colab notebook from a training dataset.

    Parameters
    ----------
    data_path : str
        Path to the training JSONL file.
    model_name : str
        HuggingFace model ID (e.g. ``unsloth/Llama-3.2-3B-Instruct-bnb-4bit``).
    preset_name : str
        Name of a Colab preset (default: ``fast-1.7b``).
    subject_spec : dict | None
        Optional subject specification dict (must contain ``npc_key``,
        ``npc_name``, ``subject``, ``system_prompt``, ``dataset``).
    hf_repo_id : str | None
        HF Hub repo ID for dataset upload. Auto-derived from ``npc_key``
        if not provided when uploading via HF mode.
    output_dir : str | None
        Directory where the notebook will be saved.
    data_mode : str | None
        Force a specific data mode (``\"drive\"``, ``\"hf\"``, or ``\"inline\"``).
        If omitted, auto-selects: ``\"drive\"`` if *drive_data_path* is set,
        else ``\"inline\"`` for datasets < 50 examples, ``\"hf\"`` otherwise.
    drive_data_path : str | None
        Google Drive path to the dataset JSONL file when using ``data_mode=\"drive\"``.
        Example: ``\"/content/drive/MyDrive/Unsloth/datasets/npc.jsonl\"``.
        The notebook mounts Drive and loads from this path.
    drive_gguf_dir : str | None
        Google Drive directory to save the exported GGUF when using
        ``data_mode=\"drive\"``. Defaults to ``\"/content/drive/MyDrive/Unsloth/gguf/\"``.

    Returns
    -------
    str
        Absolute path to the generated ``.ipynb`` file.

    Raises
    ------
    ValueError
        Subject spec is missing required keys.
    KeyError
        Preset name is unknown.
    FileNotFoundError
        Data file or Jinja2 template not found.
    PermissionError
        Output directory is not writable.
    EnvironmentError
        HuggingFace token missing or invalid when uploading.
    ConnectionError
        HF Hub upload fails after retries.
    """
    # ── Guard: validate subject spec if given ──────────────────────────────
    _REQUIRED_SPEC_KEYS = {"npc_key", "npc_name", "subject", "system_prompt", "dataset"}
    if subject_spec is not None:
        missing = _REQUIRED_SPEC_KEYS - set(subject_spec.keys())
        if missing:
            raise ValueError(
                f"Subject spec missing required key(s): {', '.join(sorted(missing))}"
            )

    # ── Determine data mode and package dataset ────────────────────────────
    if data_mode == "drive" or (data_mode is None and drive_data_path):
        data_mode = "drive"
        if not drive_data_path:
            raise ValueError(
                "drive_data_path must be provided when using data_mode='drive'"
            )
        inline_data_jsonl = ""
        hf_dataset_repo = ""
        # Use provided drive_data_path or local data_path (notebook user copies file)
        resolved_drive_data_path = drive_data_path or ""
        resolved_drive_gguf_dir = drive_gguf_dir or "/content/drive/MyDrive/Unsloth/gguf/"
        num_examples = 0  # not used in drive mode
        file_size = 0
    else:
        # ── Guard: validate data path exists (not needed for drive mode) ─
        data_path_resolved = str(Path(data_path).resolve())
        if not os.path.isfile(data_path_resolved):
            raise FileNotFoundError(f"Data file not found: {data_path_resolved}")

        num_examples, file_size = estimate_dataset_size(data_path_resolved)

        if data_mode is None:
            if num_examples < 50:
                data_mode = "inline"
            else:
                data_mode = "hf"

        if data_mode == "hf":
            # Derive repo ID from subject spec or caller argument
            if hf_repo_id is None:
                if subject_spec is not None:
                    hf_repo_id = f"npc-fit/{subject_spec['npc_key']}"
                else:
                    hf_repo_id = "npc-fit/dataset"

            token = huggingface_token or os.environ.get("HF_TOKEN")
            hf_dataset_repo = upload_to_hub(
                data_path_resolved,
                repo_id=hf_repo_id,
                token=token,
            )
            inline_data_jsonl = ""
            resolved_drive_data_path = ""
            resolved_drive_gguf_dir = ""
        else:
            inline_data_jsonl = dataset_to_inline_jsonl(data_path_resolved)
            hf_dataset_repo = ""
            resolved_drive_data_path = ""
            resolved_drive_gguf_dir = ""

    # ── Resolve preset ─────────────────────────────────────────────────────
    preset = get_colab_preset(preset_name)

    # ── Resolve output directory ───────────────────────────────────────────
    if output_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = str(project_root / "colab" / "outputs")

    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        raise PermissionError(f"Cannot create output directory: {output_dir}")

    # ── Build template variables ───────────────────────────────────────────
    # Pull metadata from subject spec or use safe defaults
    npc_name = subject_spec.get("npc_name", "NPC") if subject_spec else "NPC"
    npc_key = subject_spec.get("npc_key", "npc") if subject_spec else "npc"
    subject = subject_spec.get("subject", "") if subject_spec else ""
    system_prompt = subject_spec.get("system_prompt", "") if subject_spec else ""

    project_root = Path(__file__).resolve().parent.parent.parent
    project_url = f"file://{project_root}"

    # Pre-compute URLs to avoid complex Jinja2 string operations
    hf_data_files_url = (
        f"hf://datasets/{hf_dataset_repo}/{npc_key}.jsonl"
        if hf_dataset_repo else ""
    )
    gguf_export_dir = "colab_output-gguf-" + preset.get("quantization_method", "q4_k_m")

    template_vars = {
        "model_name": model_name,
        "hf_dataset_repo": hf_dataset_repo,
        "hf_data_files_url": hf_data_files_url,
        "gguf_export_dir": gguf_export_dir,
        "data_mode": data_mode,
        "inline_data_jsonl": inline_data_jsonl,
        "drive_data_path": resolved_drive_data_path,
        "drive_gguf_dir": resolved_drive_gguf_dir,
        "max_seq_length": preset.get("max_seq_length", 2048),
        "lora_r": preset.get("lora_r", 16),
        "lora_alpha": preset.get("lora_alpha", 32),
        "lora_dropout": preset.get("lora_dropout", 0.0),
        "use_gradient_checkpointing": "unsloth",
        "per_device_train_batch_size": preset.get("per_device_train_batch_size", 2),
        "gradient_accumulation_steps": preset.get("gradient_accumulation_steps", 4),
        "max_steps": preset.get("max_steps", -1),
        "num_train_epochs": preset.get("num_train_epochs", 3),
        "learning_rate": preset.get("learning_rate", 2e-4),
        "warmup_steps": preset.get("warmup_steps", 10),
        "weight_decay": preset.get("weight_decay", 0.01),
        "optim": "adamw_8bit",
        "lr_scheduler_type": "linear",
        "seed": 42,
        "packing": preset.get("packing", True),
        "output_dir": "colab_output",
        "npc_name": npc_name,
        "npc_key": npc_key,
        "subject": subject,
        "system_prompt": system_prompt,
        "quantization_method": "q4_k_m",
        "lora_outtype": "f16",
        "project_url": project_url,
    }

    # ── Render notebook ────────────────────────────────────────────────────
    notebook_json = render_notebook(template_vars=template_vars)

    # ── Write notebook ─────────────────────────────────────────────────────
    notebook_filename = f"{npc_key}_colab_training.ipynb"
    notebook_file = output_path / notebook_filename
    notebook_file.write_text(notebook_json, encoding="utf-8")

    # ── Print summary ──────────────────────────────────────────────────────
    print(f"\n[colab] Notebook generated: {notebook_file}")
    print(f"[colab] Model:              {model_name}")
    print(f"[colab] Preset:             {preset_name}")
    print(f"[colab] Dataset examples:   {num_examples}")
    print(f"[colab] Data mode:          {data_mode}")
    if data_mode == "hf":
        print(f"[colab] HF dataset repo:    {hf_dataset_repo}")
    print(f"[colab] Output dir:         {output_dir}")
    print()
    print("Next steps:")
    if data_mode == "drive":
        print("  1. Copy your JSONL dataset to the Drive path specified above")
        print("  2. Upload the notebook to Google Colab")
        print("  3. Connect to a T4 GPU runtime")
        print("  4. Run all cells (~5-10 min for training, ~1 min for export)")
        print("  5. Download the LoRA GGUF file from your Google Drive")
        print("  6. Copy to Unity: Assets/StreamingAssets/")
        print("  7. Load via SetLoraWeight on the LLM GameObject")
        print()
        print("  The LoRA GGUF is a small adapter (~10-30 MB).")
        print("  It loads at runtime alongside the base model in LLMUnity.")
    else:
        print("  1. Upload the notebook to Google Colab")
        print("  2. Connect to a T4 GPU runtime")
        print("  3. Run all cells (~5-10 min for training, ~1 min for export)")
        print("  4. Download the LoRA GGUF file when prompted")
        print("  5. Copy to Unity: Assets/StreamingAssets/")
        print("  6. Load via SetLoraWeight on the LLM GameObject")
        print()
        print("  The LoRA GGUF is a small adapter (~10-30 MB).")
        print("  It loads at runtime alongside the base model in LLMUnity.")

    return str(notebook_file)


__all__ = [
    "generate_colab_notebook",
    "COLAB_PRESETS",
    "get_colab_preset",
    "list_colab_presets",
]
