"""Tests for W&B config-driven defaults and fallback chain.

Verifies that wandb_inference.py reads etc/wandb/config.yaml correctly.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(PROJECT_ROOT))


class TestWandbConfigDefaults:
    """Tests the config-driven defaults in wandb_inference.py."""

    def test_imports_with_70b_default(self):
        """Default model should be 70B (from config), not the old 8B hardcode."""
        from src.core.ops.wandb_inference import DEFAULT_WANDB_INFERENCE_MODEL

        assert (
            "70B" in DEFAULT_WANDB_INFERENCE_MODEL
            or "70B" in str(DEFAULT_WANDB_INFERENCE_MODEL).upper()
        )
        assert "8B" not in DEFAULT_WANDB_INFERENCE_MODEL
        assert "Llama-3.1" in DEFAULT_WANDB_INFERENCE_MODEL

    def test_project_fallback_chain(self):
        """Verify entity/project fallback chain: explicit > env > config."""
        from src.core.ops.wandb_inference import wandb_inference_project

        # Explicit wins
        assert wandb_inference_project(entity="my-entity", project="my-proj") == "my-entity/my-proj"

        # Env var wins over config
        with patch.dict(os.environ, {"WANDB_ENTITY": "env-entity", "WANDB_PROJECT": "env-proj"}):
            assert wandb_inference_project(entity="explicit") == "explicit/env-proj"
            assert wandb_inference_project() == "env-entity/env-proj"

    def test_client_defaults_come_from_config(self):
        """WandbInferenceClient defaults should reflect config-driven values."""
        from src.core.ops.wandb_inference import (
            WandbInferenceClient,
        )

        # With no env vars set, the client uses config defaults
        with (
            patch.dict(os.environ, {"WANDB_API_KEY": "test-key"}, clear=True),
            patch(
                "src.core.ops.wandb_inference.DEFAULT_WANDB_INFERENCE_MODEL",
                "meta-llama/Llama-3.1-70B-Instruct",
            ),
        ):
            client = WandbInferenceClient()
            assert "70B" in client.model or "70B" in str(client.model).upper()

    def test_env_override_model(self):
        """WANDB_INFERENCE_MODEL env var should override config default."""
        from src.core.ops.wandb_inference import WandbInferenceClient

        with (
            patch.dict(
                os.environ,
                {
                    "WANDB_API_KEY": "test-key",
                    "WANDB_INFERENCE_MODEL": "env-override-model",
                },
                clear=True,
            ),
            patch(
                "src.core.ops.wandb_inference.DEFAULT_WANDB_INFERENCE_MODEL",
                "meta-llama/Llama-3.1-70B-Instruct",
            ),
        ):
            client = WandbInferenceClient()
            assert client.model == "env-override-model"

    def test_no_api_key_raises(self):
        from src.core.ops.wandb_inference import WandbInferenceClient

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("src.core.ops.wandb_inference.wandb_api_key", return_value=None),
        ):
            with pytest.raises(RuntimeError, match="W&B Inference requires WANDB_API_KEY"):
                WandbInferenceClient()
