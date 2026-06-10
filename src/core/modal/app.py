"""Modal app stubs for Unsloth_Core remote GPU pipeline.

STATUS: GATED — enabled=false in etc/modal/config.yaml.
Activate by setting enabled: true and running:
    modal deploy src/core/modal/app.py

Requires: MODAL_TOKEN_ID, MODAL_TOKEN_SECRET in environment.
"""

from __future__ import annotations

from src.core.modal.config import get_config, require_modal

_CONFIG = get_config()
_APP_NAME = _CONFIG.get("app", {}).get("name", "unsloth-core-pipeline")
_ENVIRONMENT = _CONFIG.get("app", {}).get("environment", "production")
_GPU_TRAINING = _CONFIG.get("gpu_profiles", {}).get("training", {}).get("type", "H100")
_GPU_EVAL = _CONFIG.get("gpu_profiles", {}).get("dataset_eval", {}).get("type", "A10G")
_TIMEOUT = _CONFIG.get("app", {}).get("timeout_seconds", 3600)

try:
    import modal

    app = modal.App(_APP_NAME)

    @app.function(
        gpu=_GPU_TRAINING,
        timeout=_TIMEOUT,
        environment=_ENVIRONMENT,
    )
    def train_remote(npc_key: str, preset: str = "fast-3b") -> dict:
        """Run training on a Modal GPU instance.

        Gated by require_modal() — raises if Modal is not enabled.
        """
        require_modal()
        # TODO: wire actual training code when Modal is activated
        return {"status": "not_implemented", "npc_key": npc_key, "preset": preset}

    @app.function(
        gpu=_GPU_EVAL,
        timeout=_TIMEOUT,
        environment=_ENVIRONMENT,
    )
    def evaluate_remote(
        npc_key: str, judge_model: str = "meta-llama/Llama-3.1-70B-Instruct"
    ) -> dict:
        """Run evaluation on a Modal GPU instance.

        Gated by require_modal() — raises if Modal is not enabled.
        """
        require_modal()
        # TODO: wire actual evaluation code when Modal is activated
        return {"status": "not_implemented", "npc_key": npc_key, "judge_model": judge_model}

    @app.function(
        gpu=_GPU_EVAL,
        timeout=_TIMEOUT,
        environment=_ENVIRONMENT,
    )
    def generate_dataset_remote(npc_key: str, technique: str = "ollama") -> dict:
        """Run dataset generation on a Modal GPU instance.

        Gated by require_modal() — raises if Modal is not enabled.
        """
        require_modal()
        # TODO: wire actual generation code when Modal is activated
        return {"status": "not_implemented", "npc_key": npc_key, "technique": technique}

except ImportError:
    # modal package not installed — stub gracefully
    app = None  # type: ignore

    def train_remote(npc_key: str, preset: str = "fast-3b") -> dict:  # type: ignore
        raise RuntimeError("modal package is not installed. Run: pip install modal")

    def evaluate_remote(npc_key: str, judge_model: str = "") -> dict:  # type: ignore
        raise RuntimeError("modal package is not installed. Run: pip install modal")

    def generate_dataset_remote(npc_key: str, technique: str = "ollama") -> dict:  # type: ignore
        raise RuntimeError("modal package is not installed. Run: pip install modal")
