#!/usr/bin/env python3
"""GPU lease model for Unsloth_Core inference lifecycle management.

Provides a lightweight, thread-safe lease system to coordinate GPU access
between train (exclusive) and judge/generation (shared) workloads.

Lease states:
    idle             — no active leases, GPU free
    judge_shared     — one or more judge leases active
    generation_shared — one or more generation leases active
    shared           — mixed judge + generation shared leases
    train_exclusive  — training holds exclusive GPU access
    blocked          — exclusive lease active, new non-lease requests rejected
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


VALID_MODES = frozenset({"judge_shared", "generation_shared", "train_exclusive"})


class LeaseConflictError(Exception):
    """Raised when a lease request conflicts with an existing active lease."""


@dataclass
class Lease:
    """A single GPU lease token."""
    id: str
    mode: str
    status: str = "active"  # active | expired | released
    ttl: int = 300
    created_at: float = 0.0
    expires_at: float = 0.0

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "status": self.status,
            "ttl": self.ttl,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired,
        }


class GpuLeaseManager:
    """Thread-safe GPU lease manager coordinating exclusive vs shared access."""

    def __init__(self) -> None:
        self._leases: dict[str, Lease] = {}
        self._lock = threading.Lock()

    def request_lease(self, mode: str, *, ttl: int = 300) -> Lease:
        """Request a GPU lease in the given mode.

        Raises:
            ValueError: if mode is invalid.
            LeaseConflictError: if a train_exclusive lease is active and prevents
                this request, or if a second train_exclusive is requested.
        """
        if mode not in VALID_MODES:
            raise ValueError(f"Invalid lease mode: {mode}. Valid modes: {sorted(VALID_MODES)}")

        with self._lock:
            self._purge_expired()

            has_exclusive = any(
                l.mode == "train_exclusive" and l.status == "active"
                for l in self._leases.values()
            )

            if mode == "train_exclusive" and has_exclusive:
                raise LeaseConflictError(
                    "Cannot acquire train_exclusive lease: another train_exclusive lease is active"
                )

            if has_exclusive:
                raise LeaseConflictError(
                    f"Cannot acquire {mode} lease: a train_exclusive lease is active"
                )

            lease_id = str(uuid.uuid4())
            now = time.time()
            lease = Lease(
                id=lease_id,
                mode=mode,
                status="active",
                ttl=ttl,
                created_at=now,
                expires_at=now + ttl,
            )
            self._leases[lease_id] = lease
            return lease

    def release_lease(self, lease_id: str) -> bool:
        """Release a lease by ID. Returns True if found and released."""
        with self._lock:
            if lease_id not in self._leases:
                return False
            self._leases[lease_id].status = "released"
            del self._leases[lease_id]
            return True

    def get_lease(self, lease_id: str) -> Lease | None:
        """Get a lease by ID, or None if not found."""
        with self._lock:
            self._purge_expired()
            return self._leases.get(lease_id)

    def status(self) -> dict[str, Any]:
        """Return current lease status summary."""
        with self._lock:
            self._purge_expired()

            active = [l.as_dict() for l in self._leases.values() if l.status == "active"]
            modes = {l["mode"] for l in active}
            has_exclusive = "train_exclusive" in modes
            has_shared = bool(modes & {"judge_shared", "generation_shared"})

            if not active:
                state = "idle"
            elif has_exclusive:
                state = "train_exclusive"
            elif has_shared and len(modes) > 1:
                state = "shared"
            elif "judge_shared" in modes:
                state = "judge_shared"
            elif "generation_shared" in modes:
                state = "generation_shared"
            else:
                state = "idle"

            return {
                "state": state,
                "active_leases": active,
                "blocked": has_exclusive,
                "lease_count": len(active),
            }

    def _purge_expired(self) -> None:
        """Remove expired leases from internal storage."""
        expired = [lid for lid, l in self._leases.items() if l.is_expired]
        for lid in expired:
            self._leases[lid].status = "expired"
            del self._leases[lid]
