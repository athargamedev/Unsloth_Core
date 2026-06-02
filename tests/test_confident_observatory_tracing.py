from src.core.tracing.confident_observatory import (
    build_npc_trace_tags,
    build_npc_trace_metadata,
    choose_observability_path,
)


def test_choose_observability_path_keeps_dataset_eval_and_tracing_separate():
    assert choose_observability_path("dataset_quality_gate")["path"] == "deepeval_test_run"
    assert choose_observability_path("runtime_npc_call")["path"] == "manual_observe"
    assert choose_observability_path("openai_runtime_call")["path"] == "native_integration_or_manual_observe"


def test_trace_tags_match_classifier_filtering_needs():
    tags = build_npc_trace_tags(
        npc_key="history_guide",
        technique="ollama",
        category="dialogue",
        turn_type="single",
        environment="dev",
    )
    assert tags == [
        "npc:history_guide",
        "technique:ollama",
        "category:dialogue",
        "turn_type:single",
        "env:dev",
        "ucore",
    ]


def test_trace_metadata_includes_classifier_and_dataset_context():
    metadata = build_npc_trace_metadata(
        npc_key="chef_assistant",
        technique="ollama",
        category="dialogue",
        concept="peanut allergy memory",
        source_path="data/datasets/chef_assistant/ollama/confident/conversational_goldens.jsonl",
        line_number=3,
        turn_type="conversational",
        classifier_hints={
            "classifier_expected_failure_mode": "Memory Retention Risk",
            "classifier_repair_priority": "P1 Training Harmful",
        },
        model="llama-3.2-3b",
        adapter="chef-lora-f16.gguf",
    )
    assert metadata["npc_key"] == "chef_assistant"
    assert metadata["turn_type"] == "conversational"
    assert metadata["classifier_expected_failure_mode"] == "Memory Retention Risk"
    assert metadata["classifier_repair_priority"] == "P1 Training Harmful"
    assert metadata["source_path"].endswith("conversational_goldens.jsonl")
    assert metadata["model"] == "llama-3.2-3b"
    assert metadata["adapter"] == "chef-lora-f16.gguf"
