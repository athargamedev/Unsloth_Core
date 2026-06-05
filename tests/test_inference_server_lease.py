from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT))


class FakeOllamaClient:
    def __init__(self):
        self.chat_calls = []
        self.stopped = []

    def status(self):
        return {"ok": True, "models": ["qwen2.5:7b"], "running_models": ["qwen2.5:7b"]}

    def chat(self, *, model, messages, format=None, options=None, keep_alive=None, timeout=None):
        self.chat_calls.append({"model": model})
        return {"message": {"content": "ok"}}

    def unload(self, model=None):
        self.stopped.append(model)
        return [model or "qwen2.5:7b"]


def test_inference_service_lease_returns_active_lease():
    """InferenceService.lease() returns an active lease with details."""
    from src.core.ops.inference_server import InferenceService

    service = InferenceService(client=FakeOllamaClient(), default_model="qwen2.5:7b")
    result = service.lease({"mode": "judge_shared", "ttl": 300})

    assert result["ok"] is True
    assert result["lease"]["mode"] == "judge_shared"
    assert result["lease"]["status"] == "active"
    assert result["lease"]["ttl"] == 300


def test_inference_service_lease_rejects_conflict():
    """InferenceService.lease() returns error on conflict instead of crashing."""
    from src.core.ops.inference_server import InferenceService

    service = InferenceService(client=FakeOllamaClient(), default_model="qwen2.5:7b")
    service.lease({"mode": "train_exclusive", "ttl": 3600})
    result = service.lease({"mode": "judge_shared", "ttl": 300})

    assert result["ok"] is False
    assert "error" in result


def test_inference_service_release_ends_lease():
    """InferenceService.release() releases a lease and returns success."""
    from src.core.ops.inference_server import InferenceService

    service = InferenceService(client=FakeOllamaClient(), default_model="qwen2.5:7b")
    created = service.lease({"mode": "judge_shared", "ttl": 300})
    lease_id = created["lease"]["id"]

    result = service.release({"lease_id": lease_id})
    assert result["ok"] is True
    assert result["released"] is True


def test_inference_service_release_nonexistent_returns_false():
    """InferenceService.release() returns released=False for invalid ID."""
    from src.core.ops.inference_server import InferenceService

    service = InferenceService(client=FakeOllamaClient(), default_model="qwen2.5:7b")
    result = service.release({"lease_id": "nonexistent"})
    assert result["ok"] is True
    assert result["released"] is False


def test_lease_status_reflects_active_leases():
    """InferenceService.status() includes lease info when leases are active."""
    from src.core.ops.gpu_lease import GpuLeaseManager
    from src.core.ops.inference_server import InferenceService

    mgr = GpuLeaseManager()
    mgr.request_lease(mode="judge_shared", ttl=300)
    service = InferenceService(
        client=FakeOllamaClient(), default_model="qwen2.5:7b", lease_manager=mgr
    )

    status = service.status()
    assert "gpu_lease" in status
    assert status["gpu_lease"]["state"] == "judge_shared"
    assert status["gpu_lease"]["lease_count"] == 1


def test_inference_service_lease_validates_mode():
    """InferenceService.lease() returns error for invalid mode."""
    from src.core.ops.inference_server import InferenceService

    service = InferenceService(client=FakeOllamaClient(), default_model="qwen2.5:7b")
    result = service.lease({"mode": "bogus", "ttl": 300})
    assert result["ok"] is False
