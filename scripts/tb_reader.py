#!/usr/bin/env python3
"""Read TensorBoard event files and return metrics as JSON.

Usage:
    python scripts/tb_reader.py --run-dir <path_to_event_folder>
"""
import argparse
import json
import os
import sys


def read_tensorboard(run_dir: str) -> dict:
    """Load TensorBoard scalars from event files in run_dir.

    Returns a dict with:
        runId, scalars (tag -> list of {step, value}), error (or null).
    """
    run_id = os.path.basename(os.path.normpath(run_dir))

    # Early exit: TensorBoard not available
    try:
        from tensorboard.backend.event_processing.event_accumulator import (
            EventAccumulator,
        )
    except ImportError:
        return {
            "runId": run_id,
            "scalars": {},
            "error": "TensorBoard not installed. pip install tensorboard",
        }

    import glob

    # Trainer logs often live in nested subdirectories such as
    # outputs/<npc>/runs/<run_id>/runs/<tb_run>/events.out.tfevents.*
    event_files = glob.glob(os.path.join(run_dir, "**", "events.out.tfevents.*"), recursive=True)
    if not event_files:
        return {
            "runId": run_id,
            "scalars": {},
            "error": "No event files found",
        }

    scalars = {}
    event_dirs = sorted({os.path.dirname(file_path) for file_path in event_files})
    for event_dir in event_dirs:
        try:
            ea = EventAccumulator(event_dir)
            ea.Reload()
        except Exception:
            continue

        for tag in ea.Tags().get("scalars", []):
            try:
                events = ea.Scalars(tag)
            except Exception:
                continue

            points = [{"step": e.step, "value": round(e.value, 6)} for e in events]
            scalars.setdefault(tag, []).extend(points)

    for tag, points in scalars.items():
        points.sort(key=lambda item: item["step"])
        scalars[tag] = points[-100:]

    return {
        "runId": run_id,
        "scalars": scalars,
        "error": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read TensorBoard event files and return metrics as JSON."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Path to the directory containing events.out.tfevents.* files",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.run_dir):
        result = {
            "runId": os.path.basename(os.path.normpath(args.run_dir)),
            "scalars": {},
            "error": f"Directory not found: {args.run_dir}",
        }
        print(json.dumps(result))
        sys.exit(0)

    result = read_tensorboard(args.run_dir)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
