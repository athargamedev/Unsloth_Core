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
    plan_payload: dict[str, Any],
    repo_url: str | None = None,
) -> dict[str, Any]:
    ds_train = f"subjects/datasets/{npc_key}/{technique}/train.jsonl"
    ds_clean = f"subjects/datasets/{npc_key}/{technique}/train_clean.jsonl"
    spec_name = Path(spec_relpath).name

    # Auto-detect repo URL from local git remote if not provided
    if repo_url is None:
        try:
            import subprocess as _sp
            result = _sp.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, check=False, timeout=5,
            )
            repo_url = (result.stdout or "").strip() or "https://github.com/athargamedev/Unsloth_Core.git"
        except Exception:
            repo_url = "https://github.com/athargamedev/Unsloth_Core.git"

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
import os
import sys
import subprocess
from pathlib import Path

REPO_URL = {repo_url!r}
DRIVE_REPO_DIR = {drive_repo_dir!r}
FALLBACK_REPO_DIR = '/content/Unsloth_Core'

# Detect if we are running in Google Colab (remote cloud runtime)
is_colab = False
try:
    import google.colab
    is_colab = True
except ImportError:
    pass

is_remote_colab = is_colab and os.path.exists('/content')

if is_remote_colab:
    print("Running in remote Google Colab runtime.")
    repo_dir = DRIVE_REPO_DIR
    try:
        from google.colab import drive
        drive.mount('/content/drive')
        print('Drive mounted, using persistent storage:', repo_dir)
    except Exception as e:
        repo_dir = FALLBACK_REPO_DIR
        print(f'Drive mount unavailable ({{e}}), using ephemeral storage:', repo_dir)

    # Clone/pull repository
    if not os.path.exists(repo_dir):
        os.makedirs(os.path.dirname(repo_dir), exist_ok=True)
        subprocess.run(['git', 'clone', REPO_URL, repo_dir], check=True)
    else:
        # Ensure it's a git repo before pulling
        git_dir = os.path.join(repo_dir, '.git')
        if os.path.exists(git_dir) and os.path.isdir(git_dir):
            orig = os.getcwd()
            os.chdir(repo_dir)
            subprocess.run(['git', 'pull'], check=False)
            os.chdir(orig)

    os.chdir(repo_dir)

    # Colab already has torch+CUDA pre-installed — install only missing deps using official fast wheels
    print("Installing Unsloth and dependencies (pre-compiled wheels for Colab)...")
    subprocess.run(['pip', 'install', '--no-deps', '-q', 'trl<0.9.0', 'peft', 'accelerate', 'bitsandbytes'], check=True)
    subprocess.run(['pip', 'install', '-q', 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'], check=True)
else:
    print("Running locally in the editor/workspace.")
    # Find local repo root by looking for ucore and scripts
    curr = Path(os.getcwd()).resolve()
    repo_dir = None
    for parent in [curr] + list(curr.parents):
        if (parent / "ucore").exists() and (parent / "scripts").exists():
            repo_dir = parent
            break
    
    if repo_dir:
        print("Detected local repository root at:", repo_dir)
        os.chdir(repo_dir)
    else:
        print("Error: Could not find local repository root containing ucore!")
        sys.exit(1)

print('Current working directory:', os.getcwd())
"""

    dataset_code = f"""
import os
import sys
import subprocess

spec = {spec_name!r}
technique = {technique!r}
train_jsonl = {ds_train!r}
clean_jsonl = {ds_clean!r}

# Use active Python executable to run ucore to avoid permission denied (exit 126) on mounted filesystems
python_bin = sys.executable

# If dataset is planned remote or missing, generate in Colab.
needs_generate = ({dataset_location!r} != 'local') or (not os.path.exists(train_jsonl))
if needs_generate:
    cmd = f"{{python_bin}} ucore generate subjects/{{spec}} --technique {{technique}}"
    print('Running:', cmd)
    subprocess.run(['bash', '-c', cmd], check=True)
else:
    print('Using existing dataset:', train_jsonl)

sanitize_cmd = f"{{python_bin}} ucore sanitize {{train_jsonl}} --output {{clean_jsonl}} --strict-canonical"
print('Running:', sanitize_cmd)
subprocess.run(['bash', '-c', sanitize_cmd], check=True)
"""

    train_code = f"""
import os
import sys
import subprocess
import urllib.request
import json
import torch

spec = {spec_name!r}
preset = {preset!r}

# Use active Python executable to run ucore to avoid permission denied (exit 126) on mounted filesystems
python_bin = sys.executable

# Detect VRAM and adjust preset if running locally on a lower-end GPU
vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3 if torch.cuda.is_available() else 0
print(f"Detected GPU VRAM: {{vram_gb:.2f}} GB")

effective_preset = preset
is_colab = False
try:
    import google.colab
    is_colab = True
except ImportError:
    pass

is_remote_colab = is_colab and os.path.exists('/content')

# If running locally on low VRAM, automatically downgrade to 'safe-any' to prevent OOM
if not is_remote_colab and vram_gb > 0 and vram_gb < 10.0 and preset == 'fast-3b':
    print("Local VRAM is low (< 10GB). Overriding preset to 'safe-any' to prevent Out-Of-Memory crashes.")
    effective_preset = 'safe-any'

# Unload Ollama models to free up VRAM if running locally
if not is_remote_colab:
    print("Attempting to unload local Ollama models to free up GPU memory...")
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps({{"model": "llama3.1:latest", "keep_alive": 0}}).encode("utf-8"),
            headers={{"Content-Type": "application/json"}}
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            print("Successfully requested Ollama to unload models.")
    except Exception as e:
        print("Ollama is not running or no models were active.")

train_cmd = f"{{python_bin}} ucore train subjects/{{spec}} --from-spec --preset {{effective_preset}} --export-gguf"
print('Running:', train_cmd)
subprocess.run(['bash', '-c', train_cmd], check=True)

print('Training + GGUF export complete!')
print('Download the GGUF using the download cell below.')
"""

    download_code = f"""
from google.colab import files
import os, glob

# Find and download the exported GGUF
gguf_dir = 'exports/{npc_key}'
ggufs = glob.glob(os.path.join(gguf_dir, '*-lora-f16.gguf'))
if ggufs:
    # Download the most recent one
    latest = max(ggufs, key=os.path.getmtime)
    print(f'Downloading: {{latest}}')
    files.download(latest)
else:
    print(f'No GGUF found in {{gguf_dir}}')
"""

    plan_json = json.dumps(plan_payload, indent=2)
    plan_cell = f"""
import json
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
        _code_cell(download_code),
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
