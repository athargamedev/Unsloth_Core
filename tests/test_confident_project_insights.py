import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def test_build_component_insights_maps_dataset_failures_to_project_root_causes(tmp_path):
    from src.core.ops.confident_insights import build_dataset_quality_insights

    summary = {
        "npc_key": "history_guide",
        "technique": "grounded",
        "status": "needs_repair",
        "total": 2,
        "failed": 2,
        "categories": {"identity": {"pass_rate": 0.0}},
    }
    failures = [
        {
            "name": "history_guide:identity:1",
            "input": "Who are you?",
            "actual_output": "I am a storyteller.",
            "metadata": {"category": "identity", "concept": "identity anchor", "line_number": 7},
            "metric": {"name": "Persona and Category Fit [GEval]", "score": 0.2, "reason": "generic identity"},
        },
        {
            "name": "history_guide:teaching:2",
            "input": "Explain sources",
            "actualOutput": "History is cool.",
            "metadata": {"category": "teaching", "concept": "primary sources", "line_number": 8},
            "metric": {"name": "Training Usefulness and Specificity [GEval]", "score": 0.3, "reason": "too generic and lacks grounded specifics"},
        },
    ]

    insights = build_dataset_quality_insights(
        summary=summary,
        failures=failures,
        npc_key="history_guide",
        technique="grounded",
        artifact_paths={"quality_summary": "quality_summary.json", "quality_failures": "quality_failures.json"},
    )

    assert insights["project"] == "Unsloth_Core"
    assert insights["npc_key"] == "history_guide"
    assert insights["component_counts"]["spec_contract"] == 1
    assert insights["component_counts"]["generator_grounding"] == 1
    assert insights["recommended_next_actions"][0]["component"] == "generator_grounding"
    assert insights["confident_payload"]["identifier"].startswith("dataset-quality:history_guide:grounded")
    assert insights["confident_payload"]["metricCollection"]["name"] == "unsloth-core-dataset-repair"
    case = insights["confident_payload"]["llmTestCases"][0]
    assert case["input"] == "Who are you?"
    assert case["actualOutput"] == "I am a storyteller."
    assert case["customColumnKeyValues"]["component"] == "spec_contract"
    assert case["customColumnKeyValues"]["repair_action"] == "tighten identity/refusal contract templates in spec or generator prompt"


def test_write_dataset_quality_insights_creates_actionable_artifact(tmp_path):
    from src.core.ops.confident_insights import write_dataset_quality_insights

    out = write_dataset_quality_insights(
        output_dir=tmp_path,
        summary={"status": "inconclusive", "null_metric_count": 3},
        failures=[{"input": "Q", "actualOutput": "A", "metadata": {"category": "dialogue"}, "metric": {"score": None, "reason": "timeout"}}],
        npc_key="chef_assistant",
        technique="grounded",
    )

    data = json.loads(out.read_text())
    assert out.name == "confident_insights.json"
    assert data["component_counts"]["judge_runner"] == 1
    assert data["recommended_next_actions"][0]["action"] == "rerun a smaller semantic gate or fix judge/Ollama availability before changing data"


def test_knowledge_retention_failures_route_to_memory_repair():
    from src.core.ops.confident_insights import build_dataset_quality_insights

    insights = build_dataset_quality_insights(
        summary={"status": "ok"},
        failures=[
            {
                "input": "Remember I am allergic to peanuts. Suggest a snack later.",
                "actualOutput": "Try peanut butter toast.",
                "metadata": {"category": "dialogue", "concept": "allergy memory"},
                "metric": {"name": "Knowledge Retention", "score": 0.1, "reason": "assistant failed to remember user allergy"},
            }
        ],
        npc_key="chef_assistant",
        technique="grounded",
    )

    assert insights["component_counts"]["memory_retention"] == 1
    assert insights["recommended_next_actions"][0]["action"] == "add multi-turn memory repair rows and verify user facts are retained across turns"
