#!/usr/bin/env python3
"""TargetRunner — holistic pipeline target planning and execution.

Orchestrates the Unsloth_Core pipeline from a high-level goal:

    target plan   ->  DAG-based cache-aware status
    target run    ->  dry-run or real execution with resume markers

The TargetRunner is the single entry point for all pipeline operations.
It wraps PipelineDAG for planning, ArtifactRegistry for artifact tracking,
RunRegistry for run lifecycle events, and GpuLeaseManager for GPU arbitration.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.core.ops.artifact_registry import ArtifactRegistry
from src.core.ops.gpu_lease import GpuLeaseManager
from src.core.ops.pipeline_dag import CANONICAL_STAGE_ORDER, PipelineDAG
from src.core.ops.run_registry import RunRegistry, make_pipeline_run_id

UCORE_CLI = Path(__file__).resolve().parent.parent.parent / "cli" / "ucore"

# Map pipeline stages to the CLI command that runs them
STAGE_COMMANDS: dict[str, list[str]] = {
    "generate":    [str(UCORE_CLI), "dataset", "generate"],
    "sanitize":    [str(UCORE_CLI), "dataset", "sanitize"],
    "dataset_eval": [str(UCORE_CLI), "dataset", "eval"],
    "train":       [str(UCORE_CLI), "train"],
    "export":      [str(UCORE_CLI), "export"],
    "evaluate":    [str(UCORE_CLI), "evaluate"],
}


class TargetRunner:
    """Orchestrate a full pipeline target from plan through execution.

    Typical usage::

        runner = TargetRunner()
        plan = runner.plan("chef_assistant", "npc-production-grounded", "ollama", "evaluate")
        cmds = runner.run(plan, dry_run=True)   # preview
        runner.run(plan, resume=True)            # execute for real
    """

    def __init__(
        self,
        *,
        artifact_index: str | Path | None = None,
        run_index: str | Path | None = None,
        dag: PipelineDAG | None = None,
        registry: ArtifactRegistry | None = None,
        run_registry: RunRegistry | None = None,
        lease_manager: GpuLeaseManager | None = None,
        verbose: bool = True,
    ) -> None:
        self.registry = registry or ArtifactRegistry(artifact_index)
        self.dag = dag or PipelineDAG(registry=self.registry)
        self.run_registry = run_registry or RunRegistry(run_index)
        self.lease_manager = lease_manager or GpuLeaseManager()
        self.verbose = verbose

    # ── Plan ───────────────────────────────────────────────────────────

    def plan(
        self,
        npc_key: str,
        profile: str,
        technique: str | None = None,
        target_stage: str = "evaluate",
    ) -> dict[str, Any]:
        """Return a full target plan with the enhanced schema."""
        base = self.dag.plan_target(target_stage, npc_key=npc_key, technique=technique)
        base["profile"] = profile
        # Compute next_required_stage if not already part of plan_target output
        if "next_required_stage" not in base:
            base["next_required_stage"] = self.dag._next_required_stage(
                target_stage, npc_key=npc_key, technique=technique
            )
        return base

    # ── Dry-run / Run ──────────────────────────────────────────────────

    def dry_run(self, plan: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the list of commands that would be executed for a plan.

        Each entry has: stage, command (list), reason, depends_on.
        """
        return self._resolve_commands(plan, dry=True)

    def run(
        self,
        plan: dict[str, Any],
        *,
        dry_run: bool = False,
        resume: bool = False,
        force_stage: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a target plan, optionally as a dry-run or resume.

        Args:
            plan: Output of TargetRunner.plan()
            dry_run: If True, print commands but don't execute.
            resume: If True, skip stages already marked complete in the run registry.
            force_stage: Re-run this specific stage even if cached.

        Returns:
            List of command results (or planned commands for dry-run).
        """
        commands = self._resolve_commands(plan, dry=dry_run)

        if not commands:
            if self.verbose:
                print("✓ All stages cached. Nothing to do.")
            return []

        # ── Acquire GPU lease for stages that need it ──────────────
        gpu_policy = plan.get("gpu_policy", {})
        active_lease_id: str | None = None
        for cmd in commands:
            stage = cmd["stage"]
            policy = gpu_policy.get(stage, {})
            if policy.get("lease_required") and active_lease_id is None:
                try:
                    lease = self.lease_manager.request_lease(
                        policy.get("lease_mode", "train_exclusive"), ttl=3600
                    )
                    active_lease_id = lease.id
                    if self.verbose:
                        print(f"  [lease] Acquired {lease.mode} lease: {lease.id}")
                except Exception as exc:
                    cmd["error"] = f"GPU lease failed: {exc}"
                    cmd["skipped"] = True
                    if self.verbose:
                        print(f"  [lease] Failed for {stage}: {exc}")
                    continue

        results: list[dict[str, Any]] = []
        for cmd in commands:
            if cmd.get("skipped"):
                results.append(cmd)
                continue

            if resume:
                stage = cmd["stage"]
                npc_key = plan["npc_key"]
                # Check if this stage is already complete in run registry
                last = self.run_registry.latest_run(npc_key, stage=stage)
                if last is not None and last.get("status") == "ok":
                    if force_stage != stage:
                        if self.verbose:
                            print(f"  [resume] Skipping {stage} — already complete")
                        cmd["skipped"] = True
                        cmd["reason"] = "resume_skip"
                        results.append(cmd)
                        continue

            if dry_run:
                results.append(cmd)
                continue

            # ── Real execution ─────────────────────────────────────
            stage = cmd["stage"]
            npc_key = plan["npc_key"]
            technique = plan.get("technique")
            profile = plan.get("profile", "default")

            run_id = make_pipeline_run_id(npc_key, stage, technique or profile)
            self.run_registry.start_run(
                run_id=run_id,
                npc_key=npc_key,
                stage=stage,
                technique=technique,
                entrypoint="target-runner",
            )

            command = cmd["command"]
            display = " ".join(shlex.quote(str(c)) for c in command)
            if self.verbose:
                print(f"  [run] {stage}: {display}")

            try:
                completed = subprocess.run(
                    command,
                    cwd=UCORE_CLI.parent.parent,
                    text=True,
                    capture_output=True,
                    timeout=3600,
                )
                if completed.returncode == 0:
                    self.run_registry.complete_run(run_id)
                    cmd["exit_code"] = 0
                    cmd["stdout"] = completed.stdout[-500:] if completed.stdout else ""
                else:
                    self.run_registry.error_run(
                        run_id,
                        error=f"exit_{completed.returncode}",
                        message=completed.stderr or "",
                    )
                    cmd["exit_code"] = completed.returncode
                    cmd["stderr"] = completed.stderr[-500:] if completed.stderr else ""
                    if self.verbose:
                        print(f"  [error] {stage} failed (exit {completed.returncode})")
                    results.append(cmd)
                    break  # Stop on first failure
            except subprocess.TimeoutExpired:
                self.run_registry.error_run(run_id, error="timeout", message="Exceeded 3600s")
                cmd["exit_code"] = -1
                cmd["error"] = "timeout"
                if self.verbose:
                    print(f"  [error] {stage} timed out")
                results.append(cmd)
                break
            except FileNotFoundError as exc:
                cmd["error"] = str(exc)
                cmd["skipped"] = True
                if self.verbose:
                    print(f"  [error] {stage} command not found: {exc}")

            results.append(cmd)

        # ── Release GPU lease ──────────────────────────────────────
        if active_lease_id is not None:
            self.lease_manager.release_lease(active_lease_id)
            if self.verbose:
                print(f"  [lease] Released lease: {active_lease_id}")

        return results

    # ── Internal helpers ──────────────────────────────────────────────

    def _resolve_commands(
        self,
        plan: dict[str, Any],
        *,
        dry: bool = False,
    ) -> list[dict[str, Any]]:
        """Map non-cached plan steps to concrete CLI commands."""
        commands: list[dict[str, Any]] = []
        seen_cached: dict[str, dict[str, Any]] = {}

        # Build cache from steps already done
        for step in plan.get("steps", []):
            if step.get("status") == "cached":
                for art in step.get("outputs") or []:
                    seen_cached[step["stage"]] = art

        for step in plan.get("steps", []):
            stage = step["stage"]
            action = step.get("action", "skip")

            if action == "skip" and step.get("status") == "cached":
                continue  # Fully cached, nothing to do

            command = list(STAGE_COMMANDS.get(stage, [str(UCORE_CLI), stage]))
            technique = plan.get("technique")
            if technique:
                command.extend(["--technique", technique])

            entry: dict[str, Any] = {
                "stage": stage,
                "command": command,
                "reason": step.get("reason", "needed"),
                "status": step.get("status", "missing"),
                "depends_on": [],
            }

            # Resolve dependencies from cache context
            required = step.get("requires", [])
            for artifact_type in required:
                for prev_stage, output in seen_cached.items():
                    if output.get("artifact_type") == artifact_type:
                        entry["depends_on"].append(prev_stage)

            commands.append(entry)

        return commands
