#!/usr/bin/env python3
"""
Generate Colab notebooks for remote_colab training plans.

Notebook cells are assembled from the existing ucore dataset/training commands,
so remote execution stays aligned with local scripts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _code_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [line + "\n" for line in source.strip("\n").split("\n")],
    }


def _md_cell(source: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [line + "\n" for line in source.strip("\n").split("\n")],
    }


def build_notebook(
    *,
    spec_relpath: str,
    preset: str,
    npc_key: str,
    technique: str,
    dataset_location: str,
    drive_repo_dir: str,
    drive_datasets_dir: str,
    plan_payload: dict[str, Any],
) -> dict[str, Any]:
    ds_train = f"subjects/datasets/{npc_key}/{technique}/train.jsonl"
    ds_clean = f"subjects/datasets/{npc_key}/{technique}/train_clean.jsonl"
    spec_name = Path(spec_relpath).name

    markdown = f"""
# Unsloth Core Colab Runner: {npc_key}

This notebook was generated from execution planning.

- Spec: `{spec_relpath}`
- Preset: `{preset}`
- Technique: `{technique}`
- Planned dataset generation location: `{dataset_location}`
- Planned training location: `remote_colab`

The commands below use the same `ucore`/`scripts` workflow as local runs.
"""

    setup_code = f"""
from google.colab import drive
import os
import subprocess

DRIVE_REPO_DIR = {drive_repo_dir!r}
DRIVE_DATASETS_DIR = {drive_datasets_dir!r}

# Mount Drive
drive.mount('/content/drive')

# Clone/pull repository in Drive-backed workspace
if not os.path.exists(DRIVE_REPO_DIR):
    os.makedirs(os.path.dirname(DRIVE_REPO_DIR), exist_ok=True)
    subprocess.run(['git', 'clone', 'https://github.com/andreathar/Unsloth_Core.git', DRIVE_REPO_DIR], check=True)

os.chdir(DRIVE_REPO_DIR)
subprocess.run(['git', 'pull'], check=False)

# Setup Python env + deps (idempotent)
subprocess.run(['python3', '-m', 'venv', 'unsloth_env'], check=False)
subprocess.run(['bash', '-lc', 'source unsloth_env/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'], check=True)
print('Repo ready at:', os.getcwd())
"""

    dataset_code = f"""
import os
import subprocess

spec = {spec_name!r}
technique = {technique!r}
train_jsonl = {ds_train!r}
clean_jsonl = {ds_clean!r}

# If dataset is planned remote or missing, generate in Colab.
needs_generate = ({dataset_location!r} != 'local') or (not os.path.exists(train_jsonl))
if needs_generate:
    cmd = f"source unsloth_env/bin/activate && ./ucore generate subjects/{{spec}} --technique {{technique}}"
    print('Running:', cmd)
    subprocess.run(['bash', '-lc', cmd], check=True)
else:
    print('Using existing dataset:', train_jsonl)

sanitize_cmd = f"source unsloth_env/bin/activate && ./ucore sanitize {{train_jsonl}} --output {{clean_jsonl}} --strict-canonical"
print('Running:', sanitize_cmd)
subprocess.run(['bash', '-lc', sanitize_cmd], check=True)
"""

    train_code = f"""
import subprocess

spec = {spec_name!r}
preset = {preset!r}

train_cmd = f"source unsloth_env/bin/activate && ./ucore train subjects/{{spec}} --from-spec --preset {{preset}}"
print('Running:', train_cmd)
subprocess.run(['bash', '-lc', train_cmd], check=True)

print('Training complete. Optional next steps: ./ucore export <npc_key> and ./ucore smoke <gguf> --spec subjects/<spec>.json')
"""

    plan_json = json.dumps(plan_payload, indent=2)
    plan_cell = f"""
# Planner payload for traceability
PLAN = {plan_json}
print(json.dumps(PLAN, indent=2))
"""

    cells = [
        _md_cell(markdown),
        _code_cell(setup_code),
        _code_cell(plan_cell),
        _code_cell(dataset_code),
        _code_cell(train_code),
    ]

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3",
            },
            "unsloth_core": {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "npc_key": npc_key,
                "preset": preset,
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def write_notebook(notebook: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(notebook, indent=2), encoding="utf-8")
    return output_path
