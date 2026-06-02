# DeepEval / Confident AI observability coherence

Status: coherent after adding Observatory contract helpers.

## Key distinction

Confident has two different flows in this repo:

1. Dataset/eval quality gates
   - Uses DeepEval `assert_test`, Confident REST `/evaluate`, and Confident Test Runs.
   - Existing commands:
     - `./ucore dataset-eval ...`
     - `./ucore dataset-eval ... --confident --remote-eval`
   - Correct for metrics like Answer Relevancy, Faithfulness, Hallucination, Knowledge Retention.
   - Classifier UI may not classify these as Observatory traces unless Confident also exposes them as traces.

2. Observatory traces/threads
   - Uses `deepeval.tracing.observe`, `update_current_trace`, `update_current_span`, and span types.
   - Correct target for Project Settings -> Classifiers.
   - Needed for runtime NPC calls, Unity/LLMUnity bridge, future local API endpoints, and conversation threads.

## Current repo state

Existing integration was mostly Test Runs / datasets:

- `src/core/dataset/dataset_eval.py`
- `tests/evals/test_dataset_generation_quality.py`
- `src/core/ops/confident_api.py`
- `src/core/dataset/confident_goldens.py`

Added Observatory contract helper:

- `src/core/tracing/confident_observatory.py`

It defines:

- `choose_observability_path()`
- `build_npc_trace_tags()`
- `build_npc_trace_metadata()`
- `observe_npc_runtime_call()`

## Coherent classifier metadata contract

Trace tags should be:

```text
npc:<npc_key>
technique:<technique>
category:<category>
turn_type:<single|conversational>
env:<dev|prod>
ucore
```

Trace metadata should include:

```json
{
  "npc_key": "history_guide",
  "technique": "ollama",
  "category": "dialogue",
  "concept": "...",
  "turn_type": "single",
  "source_path": "data/datasets/.../confident/single_turn_goldens.jsonl",
  "line_number": 12,
  "model": "llama-3.2-3b",
  "adapter": "history_guide-lora-f16.gguf",
  "dataset_alias": "ucore-history-guide-ollama-single-v1",
  "dataset_version": "20260602-...",
  "classifier_expected_failure_mode": "Vague / Low Specificity",
  "classifier_repair_priority": "P1 Training Harmful",
  "classifier_strength_hint": "Needs Review"
}
```

## Span type choice

Use these when instrumenting runtime code:

- Outer NPC turn: `@observe(type="agent", name="npc-runtime:<npc_key>")`
- Local model/LLM call: `@observe(type="llm", model="<base-or-runtime-model>")`
- Retrieval/reference lookup: `@observe(type="retriever")`
- Tools/state writes: `@observe(type="tool")`
- Dataset generation/repair helper spans: custom type like `dataset_generation` or `dataset_repair`

## Native integration vs manual observe

Use native integration when provider call supports it and gives better token/model/cost fields:

- OpenAI/Anthropic hosted runtime: native integration if available, plus an outer manual `agent` span for NPC metadata/tags.

Use manual observe when local/private/non-provider runtime:

- Ollama
- llama.cpp server
- Unity/LLMUnity
- local FastAPI endpoint
- dataset generation/eval orchestration

## Why this matters for classifiers

The classifiers you are creating are Project Settings classifiers for traces/threads. They need consistent trace tags and metadata so Confident can classify and filter:

- by NPC
- by category
- by turn type
- by candidate vs approved row
- by expected failure/repair hint
- by model/adapter/version

The previously added golden custom columns are useful for Confident datasets, but they are not a substitute for Observatory trace metadata.

## Next runtime instrumentation target

When building `ucore-local-npc-single` and `ucore-local-npc-conversation`, wrap the endpoint handler or model-call function with:

```python
from src.core.tracing.confident_observatory import observe_npc_runtime_call

@observe_npc_runtime_call(
    npc_key="history_guide",
    technique="ollama",
    category="dialogue",
    turn_type="single",
    environment="dev",
    metric_collection="npc-dataset-quality",
    metadata={"adapter": "history_guide-lora-f16.gguf"},
)
def run_npc_turn(payload):
    return {
        "actual_output": "...",
        "retrieval_context": [],
    }
```

For conversations, pass stable `thread_id` and use `turn_type="conversational"`; set metric collection to `npc-conversation-quality`.
