"""
scripts/colab/presets.py — Colab T4 (15 GB VRAM) training presets.

Presets are tuned for Google Colab's NVIDIA T4 GPU (15 GB VRAM), which
provides substantially more headroom than local RTX 3060 6 GB training.
This enables larger models (7B–14B) and higher batch sizes.
"""

from __future__ import annotations

COLAB_PRESETS: dict[str, dict] = {
    "smoke": {
        "description": "Quick smoke test (10 steps) — any model",
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 2,
        "max_steps": 10,
        "num_train_epochs": 1,
        "lora_r": 8,
        "lora_alpha": 16,
        "max_seq_length": 512,
        "packing": False,
    },
    "fast-0.5b": {
        "description": "Fast for 0.5B models on Colab T4",
        "per_device_train_batch_size": 8,
        "gradient_accumulation_steps": 1,
        "lora_r": 16,
        "lora_alpha": 32,
        "max_seq_length": 2048,
        "packing": True,
    },
    "fast-1.7b": {
        "description": "Fast for 1.7B models on Colab T4",
        "per_device_train_batch_size": 8,
        "gradient_accumulation_steps": 1,
        "lora_r": 32,
        "lora_alpha": 64,
        "max_seq_length": 4096,
        "packing": True,
    },
    "fast-3b": {
        "description": "Fast for 3B models on Colab T4 (e.g., Llama-3.2-3B)",
        "per_device_train_batch_size": 8,
        "gradient_accumulation_steps": 1,
        "lora_r": 16,
        "lora_alpha": 32,
        "max_seq_length": 4096,
        "packing": True,
    },
    "fast-8b": {
        "description": "Fast for 8B models on Colab T4 (e.g., Llama 3.1 8B) — Colab-only preset",
        "per_device_train_batch_size": 2,
        "gradient_accumulation_steps": 4,
        "lora_r": 16,
        "lora_alpha": 32,
        "max_seq_length": 2048,
        "packing": True,
    },
    "fast-14b": {
        "description": "Fast for 14B models on Colab T4 (e.g., Phi-4 14B) — Colab-only preset",
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "lora_r": 16,
        "lora_alpha": 32,
        "max_seq_length": 2048,
        "packing": True,
    },
    "safe-any": {
        "description": "Safe catch-all for any model on Colab T4",
        "per_device_train_batch_size": 1,
        "gradient_accumulation_steps": 8,
        "lora_r": 8,
        "lora_alpha": 16,
        "max_seq_length": 1024,
        "packing": True,
    },
    "quality-1.7b": {
        "description": "Higher quality for 1.7B models on Colab T4",
        "per_device_train_batch_size": 4,
        "gradient_accumulation_steps": 2,
        "num_train_epochs": 5,
        "lora_r": 32,
        "lora_alpha": 64,
        "lora_dropout": 0.05,
        "max_seq_length": 4096,
        "packing": True,
        "warmup_steps": 20,
        "learning_rate": 1e-4,
    },
    "quality-3b": {
        "description": "Higher quality for 3B models on Colab T4",
        "per_device_train_batch_size": 4,
        "gradient_accumulation_steps": 2,
        "num_train_epochs": 5,
        "lora_r": 16,
        "lora_alpha": 32,
        "lora_dropout": 0.05,
        "max_seq_length": 2048,
        "packing": True,
        "warmup_steps": 20,
        "learning_rate": 1e-4,
    },
}


def get_colab_preset(preset_name: str) -> dict:
    """Return a **copy** of the Colab preset dict for *preset_name*.

    Parameters
    ----------
    preset_name : str
        One of the keys in ``COLAB_PRESETS``.

    Returns
    -------
    dict
        A shallow copy of the preset (safe to mutate).

    Raises
    ------
    KeyError
        If *preset_name* is not found in ``COLAB_PRESETS``.
    """
    if preset_name in COLAB_PRESETS:
        return dict(COLAB_PRESETS[preset_name])

    available = ", ".join(sorted(COLAB_PRESETS))
    raise KeyError(
        f"No Colab preset mapping for '{preset_name}'. "
        f"Available presets: {available}"
    )


def list_colab_presets() -> str:
    """Return a human-readable, formatted string of all Colab presets."""
    lines = ["Available Colab T4 training presets:\n"]
    for name in sorted(COLAB_PRESETS):
        p = COLAB_PRESETS[name]
        lines.append(f"  {name:15s}  {p['description']}")
    return "\n".join(lines)
