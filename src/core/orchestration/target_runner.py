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

import shlex
import subprocess
from pathlib import Path
from typing import Any

from src.core.ops.artifact_registry import ArtifactRegistry
from src.core.ops.gpu_lease import GpuLeaseManager
from src.core.ops.pipeline_dag import (
    STAGE_OUTPUT_ARTIFACTS,
    STAGE_REQUIRED_ARTIFACTS,
    TECHNIQUE_SCOPED_ARTIFACTS,
    PipelineDAG,
    stage_input_signature,
)
from src.core.ops.run_registry import RunRegistry, make_pipeline_run_id
from src.core.orchestration.workflow_spec import WorkflowContext, build_stage_command, repo_root

UCORE_CLI = Path(__file__).resolve().parent.parent.parent / "cli" / "ucore"
PROJECT_ROOT = repo_root()


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

            if stage == "train":
                from src.core.ops.artifact_registry import ArtifactRegistry
                from src.core.training.train import training_readiness_errors

                ctx = WorkflowContext(
                    npc_key=npc_key,
                    technique=technique or "ollama",
                    profile=profile,
                )
                fresh_registry = ArtifactRegistry(self.registry.index_path)
                self.registry = fresh_registry
                self.dag = PipelineDAG(registry=self.registry)
                gate_errors = training_readiness_errors(
                    PROJECT_ROOT / ctx.clean_train_path,
                    npc_key=npc_key,
                    technique=technique,
                    registry=fresh_registry,
                )
                if gate_errors:
                    cmd["exit_code"] = 1
                    cmd["error"] = "training_gate_blocked"
                    cmd["gate_errors"] = gate_errors
                    if self.verbose:
                        print("  [blocked] train: dataset quality gate is not ready")
                        for error in gate_errors:
                            print(f"    - {error}")
                    results.append(cmd)
                    break

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
                    cwd=PROJECT_ROOT,
                    text=True,
                    capture_output=True,
                    timeout=3600,
                )
                if completed.returncode == 0:
                    self.run_registry.complete_run(run_id)
                    self._record_stage_lineage(
                        stage=stage,
                        run_id=run_id,
                        npc_key=npc_key,
                        technique=technique,
                        command=command,
                    )
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

    def _record_stage_lineage(
        self,
        *,
        stage: str,
        run_id: str,
        npc_key: str,
        technique: str | None,
        command: list[str],
    ) -> None:
        """Append a target-runner lineage record after a successful stage command."""
        self.registry = ArtifactRegistry(self.registry.index_path)
        input_records: list[dict[str, Any]] = []
        for artifact_type in STAGE_REQUIRED_ARTIFACTS.get(stage, []):
            record = self.registry.latest_artifact(
                npc_key,
                artifact_type,
                technique=technique if artifact_type in TECHNIQUE_SCOPED_ARTIFACTS else None,
            )
            if record:
                input_records.append(record)

        ctx = WorkflowContext(npc_key=npc_key, technique=technique or "ollama")
        fallback_paths = {
            "dataset_raw": ctx.raw_train_path,
            "dataset_clean": ctx.clean_train_path,
            "quality_summary": ctx.quality_summary_path,
            "adapter_checkpoint": f"artifacts/models/{npc_key}/latest",
            "gguf_adapter": ctx.adapter_gguf_path,
        }
        metadata = {
            "input_signature": stage_input_signature(stage, input_records),
            "producer_command": " ".join(shlex.quote(str(part)) for part in command),
            "recorded_by": "target-runner",
        }

        for artifact_type in STAGE_OUTPUT_ARTIFACTS.get(stage, []):
            latest = self.registry.latest_artifact(
                npc_key,
                artifact_type,
                technique=technique if artifact_type in TECHNIQUE_SCOPED_ARTIFACTS else None,
            )
            path = (latest or {}).get("path") or fallback_paths.get(artifact_type)
            if not path:
                continue
            candidate = Path(str(path))
            if not candidate.exists() and not (PROJECT_ROOT / candidate).exists():
                continue
            self.registry.record_artifact(
                run_id,
                npc_key,
                stage,
                artifact_type,
                path,
                technique=technique if artifact_type in TECHNIQUE_SCOPED_ARTIFACTS else None,
                metadata=metadata,
            )
        self.registry = ArtifactRegistry(self.registry.index_path)
        self.dag = PipelineDAG(registry=self.registry)

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

            command = build_stage_command(
                WorkflowContext(
                    npc_key=plan["npc_key"],
                    technique=plan.get("technique") or "ollama",
                    profile=plan.get("profile", "npc-production-grounded"),
                ),
                stage,
            )

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
