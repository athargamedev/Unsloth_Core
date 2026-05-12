# Phase 4 — Export & Deployment Hardening Implementation Plan

> **Goal:** Make the export → deploy → validate pipeline reliable, auditable, and Unity-ready with checksum integrity, enriched provenance, and clean CLI integration.

**Architecture:** All export paths route through `_config/paths.py`. Export metadata flows from run manifests into export manifests. Deployment validates file integrity. CLI (`ucore`) gains `export`, `deploy`, and `export-adapter` subcommands.

**Key files:**
- `scripts/export.py` — Full GGUF merge (base + LoRA)
- `scripts/export_adapter.py` — LoRA-only GGUF (for LLMUnity)
- `scripts/batch_export.py` — Batch version of export.py
- `scripts/deploy_to_unity.py` — Deploy to Unity project
- `scripts/smoke_test.py` — Post-export validation
- `_config/paths.py` — Path helpers
- `ucore` — Unified CLI
- `docs/EXPORT_WORKFLOW.md` — Existing export docs

---

### Task 1: Enrich export manifest with run provenance

**Objective:** export.py's manifest.json should read from `run_manifest.json` (not legacy `metrics.json`) and include dataset technique, eval links, and a `"provenance"` section.

**Files:**
- Modify: `scripts/export.py` (write_manifest function, lines 64-115)

**Step 1: Update manifest schema**

Current manifest has:
- npc_key, model_id, model_short, quantizations, gguf_files, exported_at, npc_name
- Optional: run_id, trained_at, training_loss, eval_perplexity (read from metrics.json)

New manifest should add:
- `"provenance"`: { git_commit, run_id, preset, dataset_technique, dataset_sha256 }
- `"evaluation"`: { win_rate, avg_quality } — read from eval_results.jsonl if available
- `"checksums"`: { "gguf_filename": "sha256:..." } for each file

**Step 2: Read from run_manifest.json instead of metrics.json**

Change the provenance lookup to read `run_manifest.json` from the latest run dir, which has richer data (git_commit, dataset_sha256, technique, preset). Fall back to `metrics.json` for backward compat.

**Step 3: Compute SHA256 for each exported GGUF**

After moving the GGUF to its final path, compute SHA256 and add to manifest:

```python
import hashlib
def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64*1024), b""):
            h.update(chunk)
    return h.hexdigest()
```

---

### Task 2: Add `ucore export` subcommand

**Objective:** `./ucore export chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit` works as a standalone command.

**Files:**
- Modify: `ucore` (main function, add subparser + handler)

**Step 1: Add subparser in ucore**

```python
export_p = subparsers.add_parser("export", help="Export trained LoRA to GGUF")
export_p.add_argument("npc_key", help="NPC key (e.g., chemistry_instructor)")
export_p.add_argument("--model", "-m", help="Base model ID")
export_p.add_argument("--quantization", default="q4_k_m", help="GGUF quantization")
export_p.add_argument("--skip-f16", action="store_true", help="Skip f16 variant")
```

**Step 2: Add handler**

```python
elif args.command == "export":
    cmd = [PYTHON, str(SCRIPTS_DIR / "export.py"), args.npc_key]
    if args.model: cmd.extend(["--model", args.model])
    if args.quantization: cmd.extend(["--quantization", args.quantization])
    if args.skip_f16: cmd.append("--skip-f16")
    run_cmd(cmd)
```

---

### Task 3: Add `ucore deploy` subcommand

**Objective:** `./ucore deploy [--unity-project /path] [--dry-run]` triggers deploy_to_unity.py.

**Files:**
- Modify: `ucore` (main function, add subparser + handler)

**Step 1: Add subparser**

```python
deploy_p = subparsers.add_parser("deploy", help="Deploy exports to Unity project")
deploy_p.add_argument("--unity-project", "-u", help="Path to Unity project")
deploy_p.add_argument("--dry-run", action="store_true", help="Show what would be done")
deploy_p.add_argument("--skip-export", action="store_true", help="Skip GGUF export step")
deploy_p.add_argument("--export-only", action="store_true", help="Only export, no copy")
```

**Step 2: Add handler**

```python
elif args.command == "deploy":
    cmd = [PYTHON, str(SCRIPTS_DIR / "deploy_to_unity.py")]
    if args.unity_project: cmd.extend(["--unity-project", args.unity_project])
    if args.dry_run: cmd.append("--dry-run")
    if args.skip_export: cmd.append("--skip-export")
    if args.export_only: cmd.append("--export-only")
    run_cmd(cmd)
```

---

### Task 4: Add `ucore export-adapter` subcommand

**Objective:** `./ucore export-adapter outputs/chemistry_instructor/` for LoRA-only GGUF export.

**Files:**
- Modify: `ucore` (main function, add subparser + handler)

**Step 1: Add subparser**

```python
ea_p = subparsers.add_parser("export-adapter", help="Export LoRA adapter as GGUF (for LLMUnity)")
ea_p.add_argument("adapter_path", help="Path to PEFT adapter directory")
ea_p.add_argument("--outtype", default="f16", choices=["f32", "f16", "bf16", "q8_0", "auto"])
ea_p.add_argument("--outfile", help="Explicit output path")
ea_p.add_argument("--all", "-a", action="store_true", help="Convert all adapters")
```

**Step 2: Add handler**

```python
elif args.command == "export-adapter":
    cmd = [PYTHON, str(SCRIPTS_DIR / "export_adapter.py")]
    if args.all:
        cmd.append("--all")
    else:
        cmd.append(args.adapter_path)
    cmd.extend(["--outtype", args.outtype])
    if args.outfile: cmd.extend(["--outfile", args.outfile])
    run_cmd(cmd)
```

---

### Task 5: Checksum validation in deploy_to_unity.py

**Objective:** After copying a GGUF to the Unity project, verify SHA256 matches the original. Report any mismatch as an error.

**Files:**
- Modify: `scripts/deploy_to_unity.py` (lines 165-175, the shutil.copy2 block)

**Step 1: Add checksum verification**

After shutil.copy2, compute SHA256 on both files and compare:

```python
import hashlib
def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64*1024), b""):
            h.update(chunk)
    return h.hexdigest()

# In deploy(), after copy2:
src_sha = file_sha256(gguf_path)
dst_sha = file_sha256(dest_path)
if src_sha != dst_sha:
    print(f"[deploy]  ✗  CHECKSUM MISMATCH: {gguf_filename}")
    print(f"[deploy]     Source: {src_sha}")
    print(f"[deploy]     Dest:   {dst_sha}")
    # Remove corrupted file
    dest_path.unlink()
    continue
print(f"[deploy]  ✓  Checksum verified: {src_sha[:16]}...")
```

---

### Task 6: Fix default Unity project path in deploy_to_unity.py

**Objective:** The current default `"Setup Guide In-Editor Tutorial"` sibling path looks like a placeholder. Update it to a sensible default or provide a better heuristic.

**Files:**
- Modify: `scripts/deploy_to_unity.py` (line 42, DEFAULT_UNITY_PATH)

**Step 1: Update the default path heuristic**

The best auto-detect is to look for sibling directories containing both `Assets/` and `ProjectSettings/`. If only one such sibling exists, use it. If multiple or none, print guidance:

```python
def auto_detect_unity_project() -> Path | None:
    """Auto-detect Unity project as a sibling directory with Assets/ + ProjectSettings/."""
    parent = PROJECT_ROOT.parent
    candidates = []
    for entry in sorted(parent.iterdir()):
        if entry.is_dir() and entry != PROJECT_ROOT:
            if (entry / "Assets").is_dir() and (entry / "ProjectSettings").is_dir():
                candidates.append(entry)
    if len(candidates) == 1:
        return candidates[0]
    elif len(candidates) > 1:
        print(f"[deploy] Multiple sibling Unity projects found: {[c.name for c in candidates]}")
        print(f"[deploy] Use --unity-project to specify.")
    return None
```

---

### Task 7: Add GGUF integrity smoke check option

**Objective:** smoke_test.py should have a `--check-integrity` flag that validates the GGUF file structure without running full inference (fast validation).

**Files:**
- Modify: `scripts/smoke_test.py` (main, add argument + handler)

**Step 1: Add argument**

```python
smoke_p.add_argument("--check-integrity", action="store_true",
                    help="Validate GGUF file structure (no inference)")
```

**Step 2: Add handler that reads GGUF header**

GGUF files have a header with magic bytes `GGUF` at offset 0. Minimal validation:

```python
import struct

def check_gguf_integrity(model_path):
    """Quick integrity check: verify GGUF magic bytes and read header fields."""
    with open(model_path, "rb") as f:
        magic = f.read(4)
        if magic != b"GGUF":
            print(f"  ✗  Invalid magic bytes: {magic.hex()}")
            return False
        version = struct.unpack("<I", f.read(4))[0]
        tensor_count = struct.unpack("<Q", f.read(8))[0]
        metadata_len = struct.unpack("<Q", f.read(8))[0]
        file_size = model_path.stat().st_size
        print(f"  ✓  Valid GGUF v{version}")
        print(f"     Tensors: {tensor_count}, Metadata: {metadata_len} bytes")
        print(f"     File size: {file_size / 1e9:.2f} GB")
    return True
```

---

### Task 8: Add "best" symlink alongside "latest" in outputs

**Objective:** `outputs/{npc_key}/best` is a symlink pointing to the best run by loss (lowest = best). Updated after each training run.

**Files:**
- Modify: `_config/paths.py` (add `best_run_dir` function)
- Modify: `scripts/train.py` (add best-symlink update after training)

**Step 1: Add best_run_dir to paths.py**

```python
def best_run_dir(npc_key: str) -> Path | None:
    """Resolve the 'best' symlink for an NPC."""
    link = output_dir(npc_key) / "best"
    if link.exists() and link.is_symlink():
        target = link.resolve()
        if target.exists():
            return target
    return None
```

**Step 2: Update best symlink after training in train.py**

After training completes and metrics are saved, scan all completed runs for the one with the lowest training loss:

```python
# After saving run_manifest.json:
# Update "best" symlink (lowest training loss wins)
best_link = paths.output_dir(npc_key) / "best"
current_loss = trainer_stats.training_loss
# Find the best run by scanning all run manifests
best_loss = current_loss
best_run = run_id
for manifest_file in sorted(paths.run_dir(npc_key, "").parent.glob("*/run_manifest.json")):
    try:
        with open(manifest_file) as f:
            m = json.load(f)
        loss = m.get("results", {}).get("training_loss")
        if loss is not None and loss < best_loss:
            best_loss = loss
            best_run = m["run_id"]
    except Exception:
        pass
# Update symlink if this run or a previous run is best
if best_run == run_id or current_loss <= best_loss:
    if best_link.exists() or best_link.is_symlink():
        best_link.unlink()
    os.symlink(f"runs/{best_run}", str(best_link), target_is_directory=True)
    print(f"  Best run: {best_run} (loss={best_loss:.4f})")
```

---

### Task 9: Update EXPORT_WORKFLOW.md and ucore --help

**Objective:** Documentation and CLI help reflect the new export/deploy subcommands and integrity checks.

**Files:**
- Modify: `docs/EXPORT_WORKFLOW.md`
- Modify: `docs/EVALUATION_WORKFLOW.md` (smoke test integrity section)

**Step 1: Add new ucore commands to EXPORT_WORKFLOW.md**

Add sections for:
- `./ucore export chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit`
- `./ucore export-adapter outputs/chemistry_instructor/`
- `./ucore deploy [--unity-project /path]`
- `./ucore smoke exports/...gguf --check-integrity`

**Step 2: Document manifest schema**

Document the enriched manifest.json schema with provenance, checksums, and evaluation sections.

---

## Verification plan

After all tasks are implemented, run:

```bash
# 1) Export with enriched manifest
./ucore export chemistry_instructor --model unsloth/Llama-3.2-3B-Instruct-bnb-4bit
cat exports/chemistry_instructor/manifest.json  # Should show provenance + checksums

# 2) GGUF integrity check
./ucore smoke exports/chemistry_instructor/chemistry_instructor-llama3.2-3b-f16.gguf --check-integrity

# 3) Deployment dry run
./ucore deploy --dry-run

# 4) ucore help shows new commands
./ucore --help  # Should list export, deploy, export-adapter

# 5) Best symlink update
ls -la outputs/chemistry_instructor/best  # Should point to best run

# 6) Commit
git add -A && git commit -m "feat: Phase 4 export/deploy hardening with integrity and CLI"
```
