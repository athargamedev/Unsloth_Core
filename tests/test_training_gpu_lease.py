"""Tests for train preflight GPU lease acquisition/release."""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))


def test_preflight_with_lease_manager_adds_lease_info():
    """run_preflight with a lease_manager returns a report containing GPU lease state."""
    from src.core.ops.gpu_lease import GpuLeaseManager
    from src.core.ops.preflight import run_preflight

    mgr = GpuLeaseManager()
    report = run_preflight(phase="train", lease_manager=mgr, auto_unload_ollama=False)

    assert report.gpu_lease_state is not None
    assert "state" in report.gpu_lease_state


def test_train_preflight_acquires_exclusive_lease():
    """Training preflight acquires a train_exclusive lease through the manager."""
    from src.core.ops.gpu_lease import GpuLeaseManager
    from src.core.ops.preflight import run_preflight

    mgr = GpuLeaseManager()
    report = run_preflight(phase="train", lease_manager=mgr, auto_unload_ollama=False)

    assert report.gpu_lease_state is not None
    assert report.gpu_lease_state["state"] == "train_exclusive"
    assert report.gpu_lease_state["blocked"] is True


def test_preflight_without_lease_manager_skips_lease():
    """run_preflight without explicit lease_manager doesn't fail — leases are optional."""
    from src.core.ops.preflight import run_preflight

    report = run_preflight(phase="train", auto_unload_ollama=False)
    # Should not crash — gpu_lease_state may be None or have a default
    assert report is not None


def test_preflight_lease_blocked_returns_error():
    """If an existing train_exclusive lease exists, preflight reports a block error."""
    from src.core.ops.gpu_lease import GpuLeaseManager
    from src.core.ops.preflight import run_preflight

    mgr = GpuLeaseManager()
    mgr.request_lease(mode="train_exclusive", ttl=3600)

    report = run_preflight(phase="train", lease_manager=mgr, auto_unload_ollama=False)
    assert report.status == "blocked"
    assert any("lease" in e.lower() for e in report.errors)


def test_preflight_dataset_eval_does_not_acquire_exclusive_lease():
    """Dataset-eval preflight does not acquire a train_exclusive lease."""
    from src.core.ops.gpu_lease import GpuLeaseManager
    from src.core.ops.preflight import run_preflight

    mgr = GpuLeaseManager()
    report = run_preflight(phase="dataset_eval", lease_manager=mgr, auto_unload_ollama=False)

    # Should not have a train_exclusive lease
    if report.gpu_lease_state:
        assert report.gpu_lease_state["state"] != "train_exclusive"


def test_preflight_lease_released_on_completion():
    """After a successful preflight, the lease can be released."""
    from src.core.ops.gpu_lease import GpuLeaseManager
    from src.core.ops.preflight import run_preflight

    mgr = GpuLeaseManager()
    report = run_preflight(phase="train", lease_manager=mgr, auto_unload_ollama=False)

    # The lease manager should have 1 active lease
    status = mgr.status()
    assert status["lease_count"] == 1
    assert status["state"] == "train_exclusive"

    # We should be able to release it
    lease_id = status["active_leases"][0]["id"]
    released = mgr.release_lease(lease_id)
    assert released is True
    assert mgr.status()["state"] == "idle"
