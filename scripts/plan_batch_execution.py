#!/usr/bin/env python3
"""
Plan execution placement in batch across subject specs and optionally generate
Colab notebooks for remote_colab items.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from plan_execution import PROJECT_ROOT, detect_local_vram_gb, parse_json, recommend
from colab_notebook_generator import build_notebook, write_notebook


def _resolve_specs(spec_glob: str, explicit_specs: list[str] | None) -> list[Path]:
    if explicit_specs:
        out: list[Path] = []
        for s in explicit_specs:
            p = Path(s)
            if not p.is_absolute():
                p = (PROJECT_ROOT / p).resolve()
            if not p.exists():
                raise SystemExit(f"Spec not found: {p}")
            out.append(p)
        return sorted(out)

    return sorted((PROJECT_ROOT).glob(spec_glob))


def _resolve_presets(presets_csv: str) -> list[str]:
    return [p.strip() for p in presets_csv.split(",") if p.strip()]


def make_batch_plan(
    specs: list[Path], presets: list[str], local_vram_gb: float | None
) -> dict[str, Any]:
    plans: list[dict[str, Any]] = []
    local_queue: list[dict[str, Any]] = []
    remote_colab_queue: list[dict[str, Any]] = []

    for spec_path in specs:
        spec = parse_json(spec_path)
        for preset in presets:
            plan = recommend(spec, preset, local_vram_gb)
            plan["spec_path"] = str(spec_path.relative_to(PROJECT_ROOT))
            plans.append(plan)

            entry = {
                "npc_key": plan["npc_key"],
                "spec_path": plan["spec_path"],
                "preset": preset,
                "technique": plan.get("technique"),
                "dataset_generation": plan["recommendation"]["dataset_generation"],
                "training": plan["recommendation"]["training"],
            }

            if plan["recommendation"]["training"]["location"] == "remote_colab":
                remote_colab_queue.append(entry)
            else:
                local_queue.append(entry)

    return {
        "local_vram_gb": local_vram_gb,
        "total_specs": len(specs),
        "total_presets": len(presets),
        "total_plan_variants": len(plans),
        "local_queue": local_queue,
        "remote_colab_queue": remote_colab_queue,
        "plans": plans,
    }


def generate_colab_notebooks(
    batch_plan: dict[str, Any],
    *,
    output_dir: Path,
    drive_repo_dir: str,
    repo_url: str | None = None,
) -> list[str]:
    written: list[str] = []

    # Generate notebooks for all variants so the user has full cloud training choices
    all_variants = batch_plan.get("remote_colab_queue", []) + batch_plan.get("local_queue", [])
    for entry in all_variants:
        npc_key = str(entry["npc_key"])
        preset = str(entry["preset"])
        technique = str(entry.get("technique") or "template")
        dataset_location = str(entry.get("dataset_generation", {}).get("location") or "local")
        spec_path = str(entry["spec_path"])

        notebook = build_notebook(
            spec_relpath=spec_path,
            preset=preset,
            npc_key=npc_key,
            technique=technique,
            dataset_location=dataset_location,
            drive_repo_dir=drive_repo_dir,
            plan_payload=entry,
            repo_url=repo_url,
        )
        out = output_dir / f"{npc_key}__{preset}__remote_colab.ipynb"
        write_notebook(notebook, out)
        written.append(str(out.relative_to(PROJECT_ROOT)))

    return written


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch planner for local vs remote_colab training")
    ap.add_argument("--spec-glob", default="subjects/NPC_specs/*.json", help="Glob under project root")
    ap.add_argument("--spec", action="append", dest="specs", help="Explicit spec path; repeatable")
    ap.add_argument("--presets", default="fast-3b", help="Comma-separated presets")
    ap.add_argument("--local-vram-gb", type=float, help="Override local VRAM GB")
    ap.add_argument("--json", action="store_true", help="Print JSON output")
    ap.add_argument("--write-plan", help="Write full plan JSON to this path")
    ap.add_argument("--generate-colab-notebooks", action="store_true", help="Generate notebooks for remote_colab queue")
    ap.add_argument("--colab-output-dir", default="colab/outputs", help="Notebook output dir")
    ap.add_argument("--drive-repo-dir", default="/content/drive/MyDrive/Unsloth_Core", help="Colab Drive repo dir")
    # note: --drive-datasets-dir removed as DRIVE_DATASETS_DIR was unused
    args = ap.parse_args()

    specs = _resolve_specs(args.spec_glob, args.specs)
    if not specs:
        raise SystemExit("No specs found")

    presets = _resolve_presets(args.presets)
    if not presets:
        raise SystemExit("No presets provided")

    local_vram = args.local_vram_gb if args.local_vram_gb is not None else detect_local_vram_gb()
    batch_plan = make_batch_plan(specs, presets, local_vram)

    notebook_paths: list[str] = []
    if args.generate_colab_notebooks:
        output_dir = Path(args.colab_output_dir)
        if not output_dir.is_absolute():
            output_dir = (PROJECT_ROOT / output_dir).resolve()
        notebook_paths = generate_colab_notebooks(
            batch_plan,
            output_dir=output_dir,
            drive_repo_dir=args.drive_repo_dir,
        )
        batch_plan["generated_colab_notebooks"] = notebook_paths

    if args.write_plan:
        plan_path = Path(args.write_plan)
        if not plan_path.is_absolute():
            plan_path = (PROJECT_ROOT / plan_path).resolve()
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(batch_plan, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(batch_plan, indent=2))
        return 0

    print("Batch Execution Plan")
    print(f"  Local VRAM:         {batch_plan['local_vram_gb']}")
    print(f"  Specs:              {batch_plan['total_specs']}")
    print(f"  Presets:            {batch_plan['total_presets']}")
    print(f"  Plan variants:      {batch_plan['total_plan_variants']}")
    print(f"  Local queue:        {len(batch_plan['local_queue'])}")
    print(f"  Remote Colab queue: {len(batch_plan['remote_colab_queue'])}")
    if notebook_paths:
        print(f"  Notebooks generated: {len(notebook_paths)}")
        for p in notebook_paths:
            print(f"    - {p}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
