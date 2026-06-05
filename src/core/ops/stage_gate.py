#!/usr/bin/env python3
"""
stage_gate.py — Inter-stage verification and checksum tracking.
Records SHA256 checksums of pipeline artifacts for integrity verification.
"""

import hashlib
import json
from pathlib import Path

STAGE_NAMES = [
    "spec",
    "generate",
    "sanitize",
    "dataset_eval",
    "train",
    "export",
    "evaluate",
    "feedback",
]


def compute_checksum(path: str | Path) -> str | None:
    """Compute SHA256 hex digest of a file. Returns None on failure."""
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def compute_checksums(paths: list[str | Path]) -> dict[str, str | None]:
    """Compute checksums for multiple files. Returns {path: sha256}."""
    return {str(p): compute_checksum(p) for p in paths}


def verify_file(path: str | Path, expected_hash: str | None = None) -> bool:
    """Verify file exists and optionally matches expected SHA256."""
    p = Path(path)
    if not p.exists():
        return False
    if not p.is_file():
        return False
    if expected_hash is not None:
        actual = compute_checksum(p)
        if actual != expected_hash:
            return False
    return True


def verify_inputs(stage_name: str, input_paths: list[str | Path]) -> list[str]:
    """Verify all input files for a stage exist. Returns list of missing files."""
    if stage_name not in STAGE_NAMES:
        return [f"Unknown stage '{stage_name}', allowed: {STAGE_NAMES}"]

    missing = []
    for p in input_paths:
        if not verify_file(p):
            missing.append(str(p))
    return missing


def load_state(manifest_path: str | Path) -> dict:
    """Load the pipeline manifest state."""
    path = Path(manifest_path)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_state(manifest_path: str | Path, state: dict) -> None:
    """Save pipeline manifest state atomically."""
    path = Path(manifest_path)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(state, indent=2))
        tmp.rename(path)
    except OSError as e:
        print(f"  [warn] Could not save stage state: {e}")


def record_stage(
    stage_name: str,
    output_paths: list[str | Path],
    manifest_path: str | Path,
    extra: dict | None = None,
) -> dict:
    """Record stage completion with file checksums in pipeline manifest."""
    state = load_state(manifest_path)
    checksums = compute_checksums(output_paths)
    entry = {
        "stage": stage_name,
        "files": {str(p): h for p, h in checksums.items()},
        "all_present": all(h is not None for h in checksums.values()),
    }
    if extra:
        entry.update(extra)

    if "stages" not in state:
        state["stages"] = []

    # Replace existing entry for same stage, or append
    for i, s in enumerate(state["stages"]):
        if s.get("stage") == stage_name:
            state["stages"][i] = entry
            break
    else:
        state["stages"].append(entry)

    state["stage_count"] = len(state["stages"])
    save_state(manifest_path, state)
    return entry


def get_stage_record(stage_name: str, manifest_path: str | Path) -> dict | None:
    """Get record for a specific stage from manifest."""
    state = load_state(manifest_path)
    for s in state.get("stages", []):
        if s.get("stage") == stage_name:
            return s
    return None


def is_stage_complete(stage_name: str, manifest_path: str | Path) -> bool:
    """Check if a stage completed successfully (all output files present)."""
    record = get_stage_record(stage_name, manifest_path)
    if record is None:
        return False
    return record.get("all_present", False) and record.get("status") != "failed"
