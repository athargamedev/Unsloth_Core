#!/usr/bin/env python3
"""
deploy_to_unity.py — Deploy Unsloth_Core GGUF LoRA exports to a Unity LLMUnity project.

Automates the full deployment pipeline:
   1. Find GGUF LoRA files in exports/<npc_key>/
  2. Optionally run export_adapter.py if GGUF not yet generated
  3. Read subject specs for NPC metadata (system_prompt, npc_name, etc.)
  4. Copy .gguf files to Unity's Assets/StreamingAssets/Models/
  5. Write a deployment manifest consumed by NPCDeploymentImporter (Unity Editor)

Usage:
    # Deploy to sibling Unity project (default relative path)
    python scripts/deploy_to_unity.py

    # Specify Unity project path explicitly
    python scripts/deploy_to_unity.py --unity-project /path/to/UnityProject

    # Skip export step (only copy already-exported GGUF files)
    python scripts/deploy_to_unity.py --skip-export

    # Dry run — show what would be done without copying
    python scripts/deploy_to_unity.py --dry-run

    # Only export GGUF (no Unity copy)
    python scripts/deploy_to_unity.py --export-only
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _config import paths


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STREAMING_ASSETS_MODELS = "Assets/StreamingAssets/Models"
MANIFEST_FILENAME = "npc_deployment_manifest.json"


def _file_sha256(path: Path) -> str:
    """Compute SHA256 hash of a file."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def find_unity_project(project_path: Path | None) -> Path | None:
    """Resolve the Unity project path. Auto-detect relative to Unsloth_Core if not specified."""
    if project_path is not None:
        target = Path(project_path).resolve()
        if (target / "Assets").is_dir() and (target / "ProjectSettings").is_dir():
            return target
        print(f"[deploy] Warning: Specified path doesn't look like a Unity project: {target}")
        return None

    # Auto-detect: find sibling directories with Assets/ + ProjectSettings/
    parent = PROJECT_ROOT.parent
    candidates = []
    for entry in sorted(parent.iterdir()):
        if entry.is_dir() and entry.resolve() != PROJECT_ROOT.resolve():
            if (entry / "Assets").is_dir() and (entry / "ProjectSettings").is_dir():
                candidates.append(entry)

    if len(candidates) == 1:
        print(f"[deploy] Auto-detected Unity project: {candidates[0]}")
        return candidates[0]
    elif len(candidates) > 1:
        print(f"[deploy] Multiple sibling Unity projects found: {[c.name for c in candidates]}")
        print(f"[deploy] Use --unity-project to specify.")
    else:
        print("[deploy] Could not auto-detect Unity project. Use --unity-project to specify.")
    return None


def find_subject_spec(npc_key: str) -> dict | None:
    """Find and load a subject JSON spec by npc_key."""
    subjects_dir = paths.subjects_root()
    candidates = [
        subjects_dir / f"{npc_key}.json",
        subjects_dir / f"{npc_key.replace('_', '-')}.json",
    ]
    for path in candidates:
        if path.exists():
            with open(path) as f:
                return json.load(f)
    return None


def scan_npcs(skip_export: bool = False, export_only: bool = False) -> list[dict]:
    """Scan exports/ directory and return info about deployable LoRAs.

    New structure:
      exports/{npc_key}/{npc_key}-{model}-{quant}.gguf

    Returns list of dicts:
        {npc_key, lora_gguf_path, adapter_dir, subject_spec}
    """
    exports_dir = paths.export_root()
    if not exports_dir.is_dir():
        print(f"[deploy] Error: exports/ directory not found at {exports_dir}")
        sys.exit(1)

    entries = []
    for entry in sorted(exports_dir.iterdir()):
        if not entry.is_dir():
            continue

        npc_key = entry.name

        # Skip colab/ — handled separately via --colab flag
        if npc_key == "colab":
            continue

        # Find GGUF files in this NPC's export directory
        gguf_files = sorted(entry.glob("*.gguf"))
        if not gguf_files:
            continue

        # Prefer q4_k_m quantized version, fall back to any GGUF
        preferred = [f for f in gguf_files if "q4_k_m" in f.name]
        gguf_path = preferred[0] if preferred else gguf_files[0]

        # Look for associated adapter in outputs/ using paths.py resolution chain
        has_adapter = False
        adapter_dir = paths.output_dir(npc_key)
        try:
            resolved_key, adapter_dir = paths.resolve_adapter_dir(npc_key)
            has_adapter = True
        except FileNotFoundError:
            pass

        # Load subject spec for metadata
        subject_spec = find_subject_spec(npc_key)

        entries.append({
            "npc_key": npc_key,
            "lora_gguf_path": str(gguf_path),
            "adapter_dir": str(adapter_dir) if has_adapter else None,
            "subject_spec": subject_spec,
        })

    return entries


def deploy(entries: list[dict], unity_project: Path, dry_run: bool = False, export_only: bool = False) -> str | None:
    """Deploy LoRA files to Unity project and generate manifest.

    Returns path to manifest file, or None if nothing was deployed.
    """
    if not entries:
        print("[deploy] No deployable LoRA entries found.")
        return None

    # Destination: Unity's Assets/StreamingAssets/Models/
    streaming_models = unity_project / STREAMING_ASSETS_MODELS
    if not dry_run:
        streaming_models.mkdir(parents=True, exist_ok=True)

    manifest_npcs = []

    for entry in entries:
        npc_key = entry["npc_key"]
        gguf_path = entry["lora_gguf_path"]
        spec = entry["subject_spec"]

        if gguf_path is None:
            print(f"[deploy]  ⚠  {npc_key}: No GGUF file to deploy (adapter dir exists but export needed)")
            continue

        gguf_filename = Path(gguf_path).name
        dest_path = streaming_models / gguf_filename
        relative_lora_path = f"Models/{gguf_filename}"

        if export_only:
            print(f"[deploy]  ✓  {npc_key}: Exported GGUF: {gguf_path} ({Path(gguf_path).stat().st_size / 1024 / 1024:.1f} MB)")
            continue

        # Copy GGUF file
        if not dry_run:
            try:
                shutil.copy2(gguf_path, dest_path)
                size_mb = dest_path.stat().st_size / (1024 * 1024)
                print(f"[deploy]  ✓  {npc_key}: Copied {gguf_filename} ({size_mb:.1f} MB) → {STREAMING_ASSETS_MODELS}/")

                # Verify checksum
                src_sha = _file_sha256(Path(gguf_path))
                dst_sha = _file_sha256(dest_path)
                if src_sha != dst_sha:
                    print(f"[deploy]  ✗  CHECKSUM MISMATCH for {gguf_filename}")
                    print(f"[deploy]     Source: {src_sha}")
                    print(f"[deploy]     Dest:   {dst_sha}")
                    dest_path.unlink(missing_ok=True)
                    continue
                print(f"[deploy]     Checksum: {src_sha[:16]}...")
            except Exception as e:
                print(f"[deploy]  ✗  {npc_key}: Copy failed: {e}")
                continue
        else:
            size_mb = Path(gguf_path).stat().st_size / (1024 * 1024)
            print(f"[deploy]  ~  {npc_key}: Would copy {gguf_filename} ({size_mb:.1f} MB) → {STREAMING_ASSETS_MODELS}/")

        # Build manifest entry
        manifest_entry = {
            "npc_key": npc_key,
            "lora_gguf": relative_lora_path,
            "gguf_full_path": str(dest_path),
        }

        if spec:
            manifest_entry["npc_name"] = spec.get("npc_name", "")
            manifest_entry["system_prompt"] = spec.get("system_prompt", "")
            manifest_entry["subject"] = spec.get("subject", "")
        else:
            manifest_entry["npc_name"] = npc_key.replace("_", " ").title()
            manifest_entry["system_prompt"] = ""
            manifest_entry["subject"] = ""

        manifest_npcs.append(manifest_entry)

    if not manifest_npcs:
        print("[deploy] No LoRAs to deploy.")
        return None

    if export_only:
        return None

    # Write manifest
    manifest = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Unsloth_Core",
        "unsloth_core_path": str(PROJECT_ROOT),
        "npcs": manifest_npcs,
    }

    manifest_path = unity_project / "Assets" / "StreamingAssets" / MANIFEST_FILENAME
    if not dry_run:
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"[deploy]  ✓  Manifest written: {manifest_path}")
    else:
        print(f"[deploy]  ~  Would write manifest: {manifest_path}")

    return str(manifest_path)


def main():
    parser = argparse.ArgumentParser(
        description="Deploy Unsloth_Core GGUF LoRA exports to a Unity LLMUnity project"
    )
    parser.add_argument(
        "--unity-project", "-u",
        help="Path to Unity project (auto-detected relative to Unsloth_Core if omitted)"
    )
    parser.add_argument(
        "--skip-export", action="store_true",
        help="Skip running export_adapter.py for directories without GGUF files"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without copying any files"
    )
    parser.add_argument(
        "--export-only", action="store_true",
        help="Only run GGUF export, skip Unity deployment"
    )
    args = parser.parse_args()

    # Step 1: Find Unity project
    unity_project = find_unity_project(
        Path(args.unity_project) if args.unity_project else None
    )
    if not args.export_only and unity_project is None:
        sys.exit(1)

    # Step 2: Scan exports/
    print(f"[deploy] Scanning {paths.export_root()} for GGUF exports...")
    entries = scan_npcs(skip_export=args.skip_export, export_only=args.export_only)
    print(f"[deploy] Found {len(entries)} candidate(s)\n")

    # Step 3: Deploy
    manifest_path = deploy(entries, unity_project, dry_run=args.dry_run, export_only=args.export_only)

    if manifest_path:
        n = 0
        with open(manifest_path) as f:
            manifest = json.load(f)
            n = len(manifest.get("npcs", []))
        print(f"\n[deploy] ✅ Deployment complete! {n} NPC(s) in manifest.")
        print(f"[deploy]    Next step: In Unity Editor, run Tools > LLM Unity > Import NPC Deployment")
    elif not args.export_only:
        print(f"\n[deploy] Nothing was deployed.")


if __name__ == "__main__":
    main()
