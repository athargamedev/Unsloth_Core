import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record) + "\n" for record in records))


def minimal_spec():
    return {
        "npc_key": "demo_npc",
        "npc_name": "DemoNpc",
        "subject": "Demo Studies",
        "system_prompt": "You are DemoNpc.",
        "dataset": {"examples_per_category": {"identity": 1}},
    }


def test_dataset_technique_priority_prefers_onyx(monkeypatch, tmp_path):
    from _config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    for technique in ("onyx", "ollama"):
        write_jsonl(paths.dataset_train_path("demo_npc", technique), [{"messages": []}])
        write_jsonl(paths.dataset_val_path("demo_npc", technique), [{"messages": []}])

    technique, train_path, val_path = paths.autodetect_dataset("demo_npc")

    assert "openai" in paths.DATASET_TECHNIQUES
    assert "anthropic" in paths.DATASET_TECHNIQUES
    assert "onyx" in paths.DATASET_TECHNIQUES
    assert technique == "onyx"
    assert train_path == paths.dataset_train_path("demo_npc", "onyx")
    assert val_path == paths.dataset_val_path("demo_npc", "onyx")



def test_ollama_generator_output_shape_is_chatml(tmp_path):
    from scripts.generate_dataset import generate_dataset

    class FakeGenerator:
        model = "fake"

        def generate(self, *args, **kwargs):
            return json.dumps({"user": "What is demo?", "assistant": "Demo is a test."})

    result_path = tmp_path / "train.jsonl"
    result = generate_dataset(minimal_spec(), result_path, include_validation=False, generator=FakeGenerator())
    first = json.loads(result_path.read_text().splitlines()[0])

    assert result["train"] == 1
    assert [m["role"] for m in first["messages"]] == ["system", "user", "assistant"]
    assert first["metadata"]["source"].startswith("ollama:")


def test_onyx_search_normalizes_local_search_response():
    from scripts.onyx_client import OnyxClient

    class FakeSession:
        def post(self, url, json, headers, timeout):
            assert url == "http://onyx.local/api/search"
            assert json["query"] == "demo topic"
            assert json["skip_query_expansion"] is True
            assert headers["Authorization"] == "Bearer test-token"

            class Response:
                status_code = 200
                text = "ok"

                def raise_for_status(self):
                    pass

                def json(self):
                    return {
                        "results": [
                            {
                                "citation_id": 7,
                                "title": "Demo Source",
                                "content": "Demo content from the index.",
                                "link": "file://demo.md",
                                "source_type": "file",
                                "updated_at": "2026-05-15",
                            }
                        ]
                    }

            return Response()

    client = OnyxClient(base_url="http://onyx.local", api_key="test-token", search_mode="search", session=FakeSession())

    results = client.search("demo topic", max_results=3)

    assert results == [
        {
            "document_id": "citation:7",
            "chunk_ind": None,
            "title": "Demo Source",
            "content": "Demo content from the index.",
            "link": "file://demo.md",
            "source_type": "file",
            "score": None,
        }
    ]


def test_onyx_dataset_generation_uses_retrieval_context_without_llm(tmp_path):
    from scripts.generate_dataset import generate_onyx_dataset

    spec = minimal_spec()
    spec["dataset"] = {"examples_per_category": {"teaching": 2}}

    class FakeOnyxClient:
        def __init__(self):
            self.queries = []

        def search(self, query, max_results=4, document_sets=None, tags=None):
            self.queries.append(query)
            return [
                {
                    "document_id": "doc-1",
                    "chunk_ind": 0,
                    "title": "Demo Source",
                    "content": "Demo studies explains demo concepts with local indexed notes.",
                    "link": "file://demo.md",
                    "source_type": "file",
                    "score": 0.91,
                }
            ]

    output_path = tmp_path / "datasets" / "demo_npc" / "onyx" / "train.jsonl"
    result = generate_onyx_dataset(
        spec,
        output_path,
        onyx_client=FakeOnyxClient(),
        include_validation=False,
        max_context_chunks=1,
        max_context_chars=220,
    )
    first = json.loads(output_path.read_text().splitlines()[0])

    assert result["train"] == 2
    assert result["categories"] == {"teaching": 2}
    assert first["metadata"]["source"] == "onyx"
    assert first["metadata"]["onyx_document_ids"] == ["doc-1"]
    assert first["metadata"]["onyx_context_chunks"] == 1
    assert "Demo Source" in first["metadata"]["onyx_titles"]
    assert "demo" in first["messages"][1]["content"].lower()
    assert "indexed notes" in first["messages"][2]["content"]


def test_smoke_custom_prompts_and_tracking_timestamp(monkeypatch, tmp_path, capsys):
    from scripts import smoke_test

    model_path = tmp_path / "model.gguf"
    model_path.write_text("stub")
    monkeypatch.setattr(sys, "argv", ["smoke_test.py", str(model_path), "--prompt", "Custom one"])
    monkeypatch.setattr(smoke_test, "run_llama_cli", lambda *args, **kwargs: "Healthy response")

    smoke_test.main()

    out = capsys.readouterr().out
    assert "Custom one" in out
    assert "1/1 prompts passed" in out


def test_tracking_local_fallback_shape(tmp_path):
    from scripts.track_eval_results import track_result

    results_file = tmp_path / "eval_results.jsonl"
    saved_to_supabase = track_result(
        "demo_npc",
        "exports/demo/model.gguf",
        win_rate=0.5,
        notes="summary",
        results_file=results_file,
        metadata={"test_type": "unit"},
    )

    record = json.loads(results_file.read_text().strip())
    assert saved_to_supabase is False
    assert record["npc_key"] == "demo_npc"
    assert record["metadata"]["test_type"] == "unit"


def test_export_latest_resolution_keeps_npc_key(monkeypatch, tmp_path):
    from _config import paths

    monkeypatch.setattr(paths, "PROJECT_ROOT", tmp_path)
    run_dir = paths.run_dir("demo_npc", "20260512_fast_001")
    run_dir.mkdir(parents=True)
    (run_dir / "adapter_config.json").write_text(json.dumps({"base_model_name_or_path": "unsloth/Test"}))
    latest = paths.output_dir("demo_npc") / "latest"
    latest.symlink_to("runs/20260512_fast_001", target_is_directory=True)

    npc_key, adapter_dir = paths.resolve_adapter_dir("demo_npc")

    assert npc_key == "demo_npc"
    assert adapter_dir == run_dir.resolve()
