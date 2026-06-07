from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_integration_audit_reports_secret_presence_without_values(monkeypatch):
    from src.core.ops.integration_audit import audit_integrations

    monkeypatch.setenv("CONFIDENT_API_KEY", "confident_secret_value")
    monkeypatch.setenv("WANDB_API_KEY", "wandb_secret_value")
    monkeypatch.setenv("MODAL_TOKEN_ID", "modal_token_id_secret")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "modal_token_secret_value")

    payload = audit_integrations(profile="npc-production-grounded")
    rendered = json.dumps(payload)

    assert payload["profile"] == "npc-production-grounded"
    assert payload["integrations"]["confident"]["credential_present"] is True
    assert payload["integrations"]["wandb"]["credential_present"] is True
    assert payload["integrations"]["modal"]["credential_present"] is True
    assert "confident_secret_value" not in rendered
    assert "wandb_secret_value" not in rendered
    assert "modal_token_id_secret" not in rendered
    assert "modal_token_secret_value" not in rendered


def test_integration_audit_cli_json_shape(monkeypatch):
    monkeypatch.setenv("CONFIDENT_API_KEY", "confident_cli_secret")
    result = subprocess.run(
        [
            sys.executable,
            "./ucore",
            "audit",
            "integrations",
            "--profile",
            "npc-production-grounded",
            "--json",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["profile"] == "npc-production-grounded"
    assert "deepeval" in payload["integrations"]
    assert "confident" in payload["integrations"]
    assert "wandb" in payload["integrations"]
    assert "modal" in payload["integrations"]
    assert "confident_cli_secret" not in result.stdout
