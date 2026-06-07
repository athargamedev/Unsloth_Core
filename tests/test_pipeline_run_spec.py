from __future__ import annotations

import json


def test_pipeline_run_spec_resolves_grounded_profile_flags():
    from src.core.orchestration.run_spec import resolve_pipeline_run_spec

    spec = resolve_pipeline_run_spec(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="evaluate",
    )
    payload = spec.to_dict()

    assert payload["schema_version"] == "1.0"
    assert payload["npc_key"] == "chef_assistant"
    assert payload["profile"] == "npc-production-grounded"
    assert payload["target_stage"] == "evaluate"
    assert payload["production"] is True
    assert payload["active_npc"] is True
    assert payload["paths"]["spec"] == "data/npcs/specs/chef_assistant.json"
    assert payload["paths"]["reference_doc"] == "data/npcs/reference_docs/chef_assistant_primer.md"
    assert payload["paths"]["report_dir"].startswith("artifacts/reports/chef_assistant/")
    assert payload["generation"]["command"] == "generate-ollama"
    assert payload["generation"]["model"] == "qwen2.5:7b"
    assert payload["dataset_eval"]["judge_provider"] == "wandb"
    assert payload["dataset_eval"]["judge_model"] == "meta-llama/Llama-3.1-70B-Instruct"
    assert payload["dataset_eval"]["mode"] == "release"
    assert payload["training"]["preset"] == "fast-3b"
    assert payload["training"]["train_on_responses_only"] is True
    assert payload["training"]["export_gguf"] is True
    assert payload["runtime_eval"]["requires_base_model"] is True
    assert payload["runtime_eval"]["report_html"] is True
    assert payload["integrations"]["confident"]["enabled"] is True
    assert payload["integrations"]["wandb"]["enabled"] is True
    assert payload["integrations"]["modal"]["enabled"] is False


def test_pipeline_run_spec_writes_json(tmp_path):
    from src.core.orchestration.run_spec import resolve_pipeline_run_spec

    spec = resolve_pipeline_run_spec(
        npc_key="chef_assistant",
        profile="npc-production-grounded",
        technique="ollama",
        target_stage="dataset_eval",
        report_dir=tmp_path / "bundle",
    )
    path = spec.write_json(tmp_path / "bundle" / "pipeline_run_spec.json")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["target_stage"] == "dataset_eval"
    assert payload["paths"]["report_dir"] == str(tmp_path / "bundle")


def test_pipeline_run_spec_rejects_inactive_npc_for_production_profile():
    import pytest

    from src.core.orchestration.run_spec import resolve_pipeline_run_spec

    with pytest.raises(ValueError, match="Inactive NPC"):
        resolve_pipeline_run_spec(
            npc_key="astronomy_guide",
            profile="npc-production-grounded",
            technique="ollama",
            target_stage="evaluate",
        )
