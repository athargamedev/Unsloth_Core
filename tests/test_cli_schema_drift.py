"""
Test: CLI ↔ TypeScript Schema Drift Detection.

Compares ``./ucore`` subcommand flags against schema definitions exported from
``scripts/export-ts-schemas.mjs``. Reports all drift (CLI flags not in
schema, schema fields not in CLI) but always passes — it is a detection
mechanism, not a hard gate.

Known drift (expected, documented here):
  - ``workflow-hooks``: global ``./ucore`` flag, not a per-subcommand arg.
    Every TS schema includes ``options.workflowHooks`` but the subparser
    actions never contain ``--workflow-hooks`` (it is on the main parser).
  - CLI/schema naming mismatches: the CLI uses shorter flag names than the
    schema (``--lr`` vs ``learning-rate``, ``--model`` vs ``model-id``, etc.).
  - ``train`` hyperparameter flags: ``--lr``, ``--batch-size``, ``--epochs``,
    etc. are set via presets by the frontend and not individually exposed in
    the schema.
  - Pipeline commands with many extra CLI convenience flags not needed by
    the frontend schema.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ═════════════════════════════════════════════════════════════════════════════
#  Known-drift catalogs
# ═════════════════════════════════════════════════════════════════════════════

# CLI command → TS schema command ID
CLI_TO_TS: dict[str, str] = {
    "audit": "audit",
    "batch-export": "batch-export",
    "compare-runs": "compare-runs",
    "dataset-eval": "dataset-eval",
    "deploy": "deploy",
    "evaluate": "evaluate",
    "export": "export",
    "export-adapter": "export-adapter",
    "export-resume": "export-resume",
    "feedback": "feedback",
    "generate": "dataset-generate",  # CLI cmd ≠ schema id
    "generate-ollama": "generate-ollama",
    "init": "init",
    "pipeline": "pipeline",
    "plan-batch": "plan-batch",
    "plan-execution": "plan-execution",
    "quick-eval": "quick-eval",
    "sanitize": "dataset-sanitize",  # CLI cmd ≠ schema id
    "smoke": "smoke",
    "supabase-check": "supabase-check",
    "tb-reader": "tb-reader",
    "track": "track",
    "train": "train",
    "validate-config": "validate-config",
    "validate-spec": "validate-spec",
}

# argparse internal dests to ignore (they're not real flags)
CLI_INTERNAL_DESTS: set[str] = {"command", "audit_command"}

# Schema fields that exist only because they are global ./ucore flags
# defined on the main parser, not on subparsers.
GLOBAL_CLI_FIELDS: set[str] = {"workflow-hooks"}

# Schema fields NOT in CLI — expected because the frontend schema uses
# naming conventions or bundled inputs different from the CLI.
# Format: {TS command id → {schema_canonical_key: "reason/CLI equivalent"}}
EXPECTED_SCHEMA_ONLY: dict[str, dict[str, str]] = {
    "audit": {
        "full": "audit check --full (sub-subparser, two levels deep)",
    },
    "dataset-generate": {
        "model-id": "CLI --model",
    },
    "dataset-sanitize": {
        "dataset-path": "CLI positional input (file path, not schema field name)",
        "output": "CLI --output",
        "dedup": "CLI --dedup",
        "spec": "CLI --spec (passed via subcommand)",
    },
    "export": {
        "model-id": "CLI --model",
        "full-merge": "CLI --full-merge",
    },
    "export-adapter": {
        "npc-key": "CLI positional adapter_path (same purpose, different arg name)",
    },
    "export-resume": {
        "model-id": "CLI --model",
    },
    "feedback": {
        # feedback takes a JSON positional; all these fields live in that JSON
        "auto-retrain": "passed via feedback JSON positional, not CLI flag",
        "baseline": "passed via feedback JSON positional",
        "deepeval-cases-per-category": "passed via feedback JSON positional",
        "deevel-judge-model": "schema typo: deepeval-judge-model",
        "deepeval-judge-model": "passed via feedback JSON positional",
        "deepeval-judge-preset": "passed via feedback JSON positional",
        "deepeval-judge-provider": "passed via feedback JSON positional",
        "deepeval-ollama-url": "passed via feedback JSON positional",
        "deepeval-soft-fail": "passed via feedback JSON positional",
        "regeneration-batch-size": "passed via feedback JSON positional",
        "regeneration-model": "passed via feedback JSON positional",
        "regeneration-preset": "passed via feedback JSON positional",
        "regeneration-technique": "passed via feedback JSON positional",
        "regeneration-url": "passed via feedback JSON positional",
        "train-preset": "passed via feedback JSON positional",
        "wandb": "CLI --wandb",
        "wandb-project": "CLI --wandb-project",
        "wandb-entity": "CLI --wandb-entity",
        "wandb-inference-project": "CLI --wandb-inference-project",
        "wandb-inference-entity": "CLI --wandb-inference-entity",
    },
    "pipeline": {
        "manifest": "CLI --docs-manifest",
    },
    "plan-batch": {
        "local-vram": "CLI --local-vram-gb",
    },
    "quick-eval": {
        "adapter-path": "CLI --adapter",
    },
    "smoke": {
        "model-path": "CLI --model",
    },
    "train": {
        "spec": "CLI positional config_or_spec",
        "model-id": "CLI --model",
        "learning-rate": "CLI --lr",
        "rank": "CLI --lora-r",
        "alpha": "CLI --lora-alpha",
        "scheduler": "CLI --lr-scheduler",
        "dataset-eval-skip": "CLI --allow-ungated-dataset",
        "export-gguf": "CLI --export-gguf",
        "full-merge-export": "CLI --full-merge-export",
        "wandb": "CLI --wandb",
        "wandb-project": "CLI --wandb-project",
        "wandb-entity": "CLI --wandb-entity",
    },
    "validate-config": {
        "data-path": "CLI --data",
    },
}

# CLI-only flags per command — expected because the CLI exposes many
# internal/advanced flags the frontend schema doesn't need.
EXPECTED_CLI_ONLY: dict[str, set[str]] = {
    "audit": {"audit-command"},  # sub-subparser dest
    "batch-export": set(),
    "compare-runs": set(),
    "dataset-eval": {"confident", "pull-alias", "remote-eval"},
    "deploy": set(),
    "evaluate": {"confident", "remote-eval"},
    "export": {"maximum-memory", "outtype", "resume", "skip-f16", "model"},
    "export-adapter": {"all", "outfile", "outtype", "adapter-path"},
    "export-resume": {"skip-f16", "timeout-seconds", "model"},
    "feedback": {
        "dry-run",
        "auto",
        "skip-gap-detection",
        "save-gaps",
        "win-rate-threshold",
        "quality-threshold",
        "violation-threshold",
    },
    "generate": {"ollama", "concept-focus", "docs-manifest", "fresh"},
    "generate-ollama": {
        "check-health",
        "concept-focus",
        "dry-run",
        "fresh",
        "no-validation",
        "output",
        "pull-model",
        "val-split",
    },
    "init": {"force", "skip-spec"},
    "pipeline": {"confident", "remote-eval", "docs-manifest"},
    "plan-batch": {
        "colab-output-dir",
        "drive-repo-dir",
        "generate-colab-notebooks",
        "json",
        "local-vram-gb",
        "spec",
        "write-plan",
    },
    "plan-execution": {"json"},
    "quick-eval": {"feedback-json", "output", "wandb", "wandb-project", "wandb-entity", "adapter"},
    "sanitize": {
        "input",
        "min-length",
        "max-sentences",
        "verbose",
        "strict-canonical",
        "strict-mode",
        "artifact-check",
    },
    "smoke": {"check-integrity", "track", "model"},
    "supabase-check": {"skip-probe"},
    "tb-reader": set(),
    "track": set(),
    "train": {
        "config-or-spec",
        "from-spec",
        "lr",
        "batch-size",
        "epochs",
        "grad-accum",
        "max-seq-len",
        "lora-r",
        "lora-alpha",
        "lora-dropout",
        "neftune",
        "weight-decay",
        "warmup",
        "lr-scheduler",
        "packing",
        "train-on-responses",
        "quantization",
        "allow-ungated-dataset",
        "model",
        "no-wandb",
        "wandb-project",
        "wandb-entity",
        "export-gguf",
        "full-merge-export",
    },
    "validate-config": {
        "config",
        "data",
        "format",
        "model",
        "npc-key",
        "output",
        "require-canonical",
        "strict",
    },
    "validate-spec": {
        "all",
        "generation-ready",
        "json",
        "require-all-categories",
        "require-dataset-minimums",
        "require-reference-contract",
        "require-reference-docs",
        "strict",
    },
}


# ═════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═════════════════════════════════════════════════════════════════════════════


def camel_to_kebab(name: str) -> str:
    """Convert camelCase → kebab-case."""
    s1 = re.sub(r"([a-z])([A-Z])", r"\1-\2", name)
    return s1.lower()


def schema_key_to_canonical(field_key: str) -> str:
    """Normalise ``options.batchSize`` → ``batch-size``."""
    inner = field_key.removeprefix("options.")
    return camel_to_kebab(inner)


def load_ucore():
    """Dynamically import the ``ucore`` script (no ``.py`` extension)."""
    ucore_path = PROJECT_ROOT / "ucore"
    loader = importlib.machinery.SourceFileLoader("ucore", str(ucore_path))
    spec = importlib.util.spec_from_loader("ucore", loader, origin=str(ucore_path))
    mod = importlib.util.module_from_spec(spec)
    mod.__file__ = str(ucore_path)
    loader.exec_module(mod)
    return mod


def get_ts_schemas() -> dict[str, Any]:
    """Run the Node.js schema exporter and return parsed JSON."""
    script_path = PROJECT_ROOT / "scripts" / "export-ts-schemas.mjs"
    result = subprocess.run(
        ["node", str(script_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


# ═════════════════════════════════════════════════════════════════════════════
#  The test
# ═════════════════════════════════════════════════════════════════════════════

# We disable pytest's capsys in this test because we print a multi-section
# drift report that must reach stdout even on success.


def test_cli_schema_drift(capsys):
    """Compare CLI flags against TS schema entries.  Always passes —
    reports drift for human review rather than blocking CI."""
    ucore = load_ucore()
    parser = ucore.create_parser()
    ts_schemas = get_ts_schemas()

    subparsers_action = parser._subparsers._group_actions[0]
    cli_commands: dict[str, Any] = subparsers_action.choices

    all_entries: list[dict[str, Any]] = []
    cli_only_unexpected: list[tuple[str, str]] = []
    schema_only_unexpected: list[tuple[str, str]] = []

    for cli_cmd in sorted(cli_commands):
        ts_cmd = CLI_TO_TS.get(cli_cmd)
        if ts_cmd is None or ts_cmd not in ts_schemas:
            continue

        subparser = cli_commands[cli_cmd]

        # --- collect CLI flags ---
        cli_flags: set[str] = set()
        for action in subparser._actions:
            if action.option_strings and "--help" in action.option_strings:
                continue
            if action.option_strings:
                # BooleanOptionalAction: --dedup / --no-dedup → canonical form
                flag = next(
                    (s.lstrip("-") for s in action.option_strings if not s.startswith("--no-")),
                    action.option_strings[0].lstrip("-"),
                )
                cli_flags.add(flag)
            else:
                dest_normal = action.dest.replace("_", "-")
                if dest_normal not in CLI_INTERNAL_DESTS:
                    cli_flags.add(dest_normal)

        # --- collect schema fields ---
        schema = ts_schemas[ts_cmd]
        schema_flags: set[str] = set()
        for field_key in schema:
            schema_flags.add(schema_key_to_canonical(field_key))

        # --- compute drift ---
        only_in_cli = cli_flags - schema_flags - GLOBAL_CLI_FIELDS
        only_in_schema = schema_flags - cli_flags - GLOBAL_CLI_FIELDS

        # Apply known-exception catalogs
        known_cli = EXPECTED_CLI_ONLY.get(cli_cmd, set())
        unexpected_cli = only_in_cli - known_cli

        known_schema = EXPECTED_SCHEMA_ONLY.get(ts_cmd, {})
        unexpected_schema = only_in_schema - set(known_schema.keys())

        if not only_in_cli and not only_in_schema:
            continue

        entry: dict[str, Any] = {
            "command": cli_cmd,
            "ts_cmd": ts_cmd,
            "only_in_cli": sorted(only_in_cli),
            "only_in_schema": sorted(only_in_schema),
            "unexpected_cli": sorted(unexpected_cli),
            "unexpected_schema": sorted(unexpected_schema),
        }
        all_entries.append(entry)

        for fl in unexpected_cli:
            cli_only_unexpected.append((cli_cmd, fl))
        for fl in unexpected_schema:
            schema_only_unexpected.append((cli_cmd, fl))

    # ── Print drift report ──────────────────────────────────────────────
    matched = sum(1 for c in cli_commands if CLI_TO_TS.get(c) in ts_schemas)

    with capsys.disabled():
        print(f"\n{'=' * 68}")
        print("   CLI ↔ Schema Drift Report")
        print(f"{'=' * 68}")
        print(f"   CLI commands found:         {len(cli_commands)}")
        print(f"   Matched to TS schemas:      {matched}")
        print(f"   Commands with any drift:    {len(all_entries)}")
        print(f"   Unexpected CLI-only flags:  {len(cli_only_unexpected)}")
        print(f"   Unexpected schema-only flds:{len(schema_only_unexpected)}")
        print()

        if not all_entries:
            print("   ✓ No drift detected.\n")
            return

        for entry in all_entries:
            cmd = entry["command"]
            print(f"   ── [{cmd}] ──")

            if entry["only_in_cli"]:
                tag = (
                    " (expected)"
                    if not entry["unexpected_cli"]
                    else ("" if not entry["only_in_schema"] else "")
                )
                print(f"    CLI-only flags{tag}:")
                for fl in entry["only_in_cli"]:
                    expect = "✓" if fl in EXPECTED_CLI_ONLY.get(cmd, set()) else "⚠"
                    print(f"      {expect} {fl}")

            if entry["only_in_schema"]:
                print("    Schema-only fields:")
                known_s = EXPECTED_SCHEMA_ONLY.get(entry["ts_cmd"], {})
                for fl in entry["only_in_schema"]:
                    reason = known_s.get(fl, "UNEXPECTED — no CLI equivalent")
                    expect = "✓" if fl in known_s else "⚠"
                    print(f"      {expect} {fl}  ← {reason}")

        print()
        print("   ── Summary ──")
        print(
            f"   CLI-only: {len(cli_only_unexpected)} unexpected "
            f"(out of {sum(len(e['only_in_cli']) for e in all_entries)} total)"
        )
        print(
            f"   Schema-only: {len(schema_only_unexpected)} unexpected "
            f"(out of {sum(len(e['only_in_schema']) for e in all_entries)} total)"
        )

        if not cli_only_unexpected and not schema_only_unexpected:
            print("   ✓ All drift accounted for in known-exception catalogs.")
        else:
            print("   ⚠ Unexplained drift — review entries marked ⚠ above.")

    # ── Fail?  YES, but only on UNEXPECTED drift ──────────────────────
    msg_parts: list[str] = []
    if cli_only_unexpected:
        msg_parts.append(
            f"CLI-only ({len(cli_only_unexpected)}):\n"
            + "\n".join(f"  {c}: --{f}" for c, f in cli_only_unexpected)
        )
    if schema_only_unexpected:
        msg_parts.append(
            f"Schema-only ({len(schema_only_unexpected)}):\n"
            + "\n".join(f"  {c}: {f}" for c, f in schema_only_unexpected)
        )

    if msg_parts:
        pytest.fail("Unexpected CLI↔Schema drift detected.\n\n" + "\n\n".join(msg_parts))
