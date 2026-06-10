# Confident AI Integration Workflow

## Overview
This document describes the integration of Confident AI with the Unsloth_Core NPC pipeline for dataset management, multi-turn evaluation, observability, and classifier feedback.

## Dataset Push Workflow

We maintain Confident-native golden projections separate from raw ChatML SFT JSONL datasets to support dataset review, eval linkage, regression, and custom columns.

### 1. Golden Types
- **Single-turn goldens** (`data/datasets/<npc>/<technique>/confident/single_turn_goldens.jsonl`):
  Uses `input`, `expectedOutput`, `context`, `customColumnKeyValues`, `additionalMetadata`.
  *Note: Only populate `expectedOutput` if the row is approved as ideal behavior. Never use `actualOutput` for generated training data.*
- **Conversational goldens** (`data/datasets/<npc>/<technique>/confident/conversational_goldens.jsonl`):
  Uses `scenario`, `userDescription`, `turns`, `customColumnKeyValues`. For memory retention, prioritize providing opening seed turns and scenario outcomes over complete conversations.

### 2. Pushing to Confident AI
Push datasets using the MCP tool with `finalized: true` to commit them for evaluation. Unfinalized (`finalized: false`) places them in a candidate queue for review.

```python
# Push single-turn
mcp0_push_dataset(
    request={
        "alias": "ucore-<npc>-<technique>-single-v1",
        "finalized": True,
        "goldens": [...]
    }
)

# Push conversational
mcp0_push_dataset(
    request={
        "alias": "ucore-<npc>-<technique>-conversation-v1",
        "finalized": True,
        "conversationalGoldens": [...]
    }
)
```

## AI Connection Setup (No-Code Evaluation)

AI Connections allow Confident UI to directly query a local running NPC endpoint for trace evaluation.

1. **Start the local server**: `python src/npc_server/server.py`
2. **Configure AI Connection** in Confident (Project Settings -> AI Connections):
   - **Endpoint**: `http://localhost:8000/generate`
   - **Mode**: HTTP Response
   - **Payload**:
     ```json
     {
       "input": golden.input,
       "context": golden.context,
       "hyperparameters": { "npc_key": "history_guide" }
     }
     ```
   - **Actual Output Key Path**: `output`

## Observability Coherence (Traces & Classifiers)

We use Observatory traces to track local model calls, dataset generation, and runtime NPC responses. 

### Trace Constraints
When wrapping handlers with DeepEval traces (`@observe` or equivalent helpers), trace tags should follow a structured format:
- `npc:<npc_key>`
- `technique:<technique>`
- `category:<category>`
- `turn_type:<single|conversational>`

### Recommended Classifiers
Configure these classifiers in Confident UI to tag threads and traces effectively:
1. **NPC Dataset Failure Mode**: Labels like `Vague / Low Specificity`, `Role Drift`, `Constraint Violation`, `Grounding Gap / Possible Hallucination`.
2. **NPC Dataset Strength**: Labels like `Concrete Teaching`, `Strong Persona Fit`, `Good Runtime Fit`.
3. **NPC Repair Priority**: Labels like `P0 Safety/Factual Risk`, `P1 Training Harmful`, `P2 Improve Later`, `No Repair Needed`.

## Evaluation Metric Collections

Group remote metrics strategically in Confident:
- **`npc-dataset-quality`**: Single-turn eval (Answer Relevancy, Faithfulness, Hallucination).
- **`npc-conversation-quality`**: Multi-turn eval (Role Adherence, Knowledge Retention, Conversation Completeness).
- **`npc-runtime-quality`**: Unity/runtime behavioral checks.
