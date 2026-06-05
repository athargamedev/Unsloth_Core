from src.core.dataset.ollama_orchestrator import OllamaDatasetGenerator


class DummyHooks:
    def __init__(self):
        self.events = []

    def emit(self, step, status, **fields):
        self.events.append((step, status, fields))


def test_emit_hook_records_event():
    gen = object.__new__(OllamaDatasetGenerator)
    gen.hook_recorder = DummyHooks()
    gen._emit_hook("generate_example", "start", category="dialogue", concept="x")
    assert gen.hook_recorder.events == [
        ("generate_example", "start", {"category": "dialogue", "concept": "x"})
    ]
