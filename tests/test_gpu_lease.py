from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import UUID

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(PROJECT_ROOT))


def test_lease_manager_starts_idle():
    """A fresh GpuLeaseManager reports idle status and no leases."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    status = mgr.status()
    assert status["state"] == "idle"
    assert status["active_leases"] == []
    assert status["blocked"] is False


def test_request_judge_shared_lease_returns_active_lease():
    """Requesting a judge_shared lease returns an active lease with proper fields."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    lease = mgr.request_lease(mode="judge_shared", ttl=300)

    assert lease.mode == "judge_shared"
    assert lease.ttl == 300
    assert lease.status == "active"
    assert lease.id is not None
    assert lease.created_at > 0
    assert lease.expires_at > lease.created_at
    # Validate UUID
    UUID(lease.id)


def test_request_train_exclusive_lease_returns_active_lease():
    """Requesting a train_exclusive lease returns an active lease."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    lease = mgr.request_lease(mode="train_exclusive", ttl=3600)

    assert lease.mode == "train_exclusive"
    assert lease.status == "active"


def test_train_exclusive_blocks_second_lease():
    """A second train_exclusive lease request is rejected while one is active."""
    from src.core.ops.gpu_lease import GpuLeaseManager, LeaseConflictError

    mgr = GpuLeaseManager()
    mgr.request_lease(mode="train_exclusive", ttl=3600)

    with pytest.raises(LeaseConflictError) as exc:
        mgr.request_lease(mode="train_exclusive", ttl=300)
    assert "train_exclusive" in str(exc.value)


def test_train_exclusive_blocks_judge_shared():
    """judge_shared lease is rejected while train_exclusive is active."""
    from src.core.ops.gpu_lease import GpuLeaseManager, LeaseConflictError

    mgr = GpuLeaseManager()
    mgr.request_lease(mode="train_exclusive", ttl=3600)

    with pytest.raises(LeaseConflictError) as exc:
        mgr.request_lease(mode="judge_shared", ttl=300)
    assert "train_exclusive" in str(exc.value)


def test_judge_and_generation_shared_can_coexist():
    """Multiple shared leases (judge + generation) can be active simultaneously."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    l1 = mgr.request_lease(mode="judge_shared", ttl=300)
    l2 = mgr.request_lease(mode="generation_shared", ttl=300)

    assert l1.status == "active"
    assert l2.status == "active"

    status = mgr.status()
    assert len(status["active_leases"]) == 2
    assert status["state"] == "shared"


def test_release_lease_ends_it_and_frees_capacity():
    """After releasing a lease, a new train_exclusive lease can be acquired."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    l1 = mgr.request_lease(mode="judge_shared", ttl=300)
    assert mgr.release_lease(l1.id) is True

    # Now train_exclusive should work
    l2 = mgr.request_lease(mode="train_exclusive", ttl=3600)
    assert l2.status == "active"


def test_release_nonexistent_lease_returns_false():
    """releasing a lease that doesn't exist returns False."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    assert mgr.release_lease("nonexistent-id") is False


def test_expired_lease_removed_on_status_check():
    """An expired lease is cleaned up automatically during status() call."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    lease = mgr.request_lease(mode="judge_shared", ttl=-1)  # Already expired

    status = mgr.status()
    assert len(status["active_leases"]) == 0
    assert status["state"] == "idle"


def test_status_reflects_blocked_state():
    """status() reports blocked=True when train_exclusive is active."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    mgr.request_lease(mode="train_exclusive", ttl=3600)

    status = mgr.status()
    assert status["blocked"] is True
    assert status["state"] == "train_exclusive"


def test_status_reflects_shared_state():
    """status() reports shared state when non-exclusive leases are active."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    mgr.request_lease(mode="judge_shared", ttl=300)
    mgr.request_lease(mode="generation_shared", ttl=300)

    status = mgr.status()
    assert status["blocked"] is False
    assert status["state"] == "shared"


def test_invalid_mode_raises_value_error():
    """Requesting a lease with an invalid mode raises ValueError."""
    from src.core.ops.gpu_lease import GpuLeaseManager

    mgr = GpuLeaseManager()
    try:
        mgr.request_lease(mode="invalid_mode", ttl=300)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "invalid_mode" in str(e).lower() or "mode" in str(e).lower()
