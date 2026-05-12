"""
scripts/colab/dataset_packager.py — Dataset packaging for Colab notebooks.

Provides three operations:
1. **Upload** a JSONL dataset to HuggingFace Hub for ``data_mode="hf"``.
2. **Inline** a small JSONL dataset as an embedded string for ``data_mode="inline"``.
3. **Estimate** dataset size (number of examples, file bytes).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def estimate_dataset_size(data_path: str) -> tuple[int, int]:
    """Return ``(num_examples, file_size_bytes)`` for a JSONL dataset file.

    Parameters
    ----------
    data_path : str
        Path to a ``.jsonl`` file (newline-delimited JSON).

    Returns
    -------
    tuple[int, int]
        Number of lines (examples) and file size in bytes.

    Raises
    ------
    FileNotFoundError
        *data_path* does not exist.
    ValueError
        *data_path* is empty or not valid JSONL.
    """
    path = Path(data_path)

    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {data_path}")

    file_size = path.stat().st_size

    if file_size == 0:
        raise ValueError(f"Dataset file is empty: {data_path}")

    num_examples = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL at line {num_examples + 1} in {data_path}: {exc}"
                )
            num_examples += 1

    if num_examples == 0:
        raise ValueError(f"Dataset file contains no valid JSON lines: {data_path}")

    return num_examples, file_size


def dataset_to_inline_jsonl(data_path: str) -> str:
    """Read a JSONL dataset and return its content as a single string.

    Parameters
    ----------
    data_path : str
        Path to a ``.jsonl`` file.

    Returns
    -------
    str
        The raw text content of the file, suitable for embedding in a
        Colab notebook as a Python string literal.

    Raises
    ------
    FileNotFoundError
        *data_path* does not exist.
    """
    path = Path(data_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {data_path}")
    return path.read_text(encoding="utf-8")


def upload_to_hub(
    data_path: str,
    repo_id: str,
    token: str | None = None,
    hf_token: str | None = None,
) -> str:
    """Upload a JSONL dataset to HuggingFace Hub as a Dataset.

    Parameters
    ----------
    data_path : str
        Path to the local ``.jsonl`` file.
    repo_id : str
        Target HF Hub repository ID (e.g. ``npc-fit/chemistry_instructor``).
    token : str | None
        HuggingFace API token.  Falls back to ``HF_TOKEN`` env var.
    hf_token : str | None
        Alias for *token* (convenience).

    Returns
    -------
    str
        The ``repo_id`` of the uploaded dataset.

    Raises
    ------
    EnvironmentError
        No valid HuggingFace token found.
    ConnectionError
        Network or API failure after retries.
    """
    from huggingface_hub import HfApi, create_repo, upload_file

    # ── Resolve token ──────────────────────────────────────────────────
    resolved_token = token or hf_token or os.environ.get("HF_TOKEN")
    if not resolved_token:
        raise EnvironmentError(
            "HuggingFace token missing or invalid. "
            "Provide ``huggingface_token``, ``hf_token``, or set the "
            "``HF_TOKEN`` environment variable."
        )

    # ── Guard: validate data file ──────────────────────────────────────
    path = Path(data_path)
    if not path.is_file():
        raise FileNotFoundError(f"Dataset file not found: {data_path}")

    # ── Create the repo (idempotent) ───────────────────────────────────
    api = HfApi()
    try:
        create_repo(
            repo_id=repo_id,
            token=resolved_token,
            repo_type="dataset",
            exist_ok=True,
        )
    except Exception as exc:
        raise ConnectionError(
            f"Failed to create or verify HF Hub repo '{repo_id}': {exc}"
        )

    # ── Upload the file ────────────────────────────────────────────────
    remote_path = path.name  # e.g. ``chemistry_instructor.jsonl``
    max_retries = 3
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            upload_file(
                path_or_fileobj=str(path),
                path_in_repo=remote_path,
                repo_id=repo_id,
                repo_type="dataset",
                token=resolved_token,
            )
            break
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(2 ** attempt)  # exponential back-off
    else:
        raise ConnectionError(
            f"HF Hub upload failed after {max_retries} retries. "
            f"Last error: {last_error}"
        )

    # ── Warn for very small datasets ───────────────────────────────────
    num_examples, _ = estimate_dataset_size(data_path)
    if num_examples < 5:
        print(
            f"[colab] Warning: Dataset has only {num_examples} example(s). "
            f"Uploading to Hub anyway, but consider adding more data."
        )

    return repo_id
