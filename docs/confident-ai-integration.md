# Confident AI Integration Workflow

## Overview

This document describes the integration of Confident AI MCP tools with the Unsloth_Core NPC training pipeline for dataset management and evaluation.

## Dataset Push Workflow

### 1. Prepare Goldens

Goldens are stored in `data/datasets/<npc>/<technique>/confident/`:

- **Single-turn goldens**: `single_turn_goldens.jsonl`
  - Format: JSONL with keys `input`, `expectedOutput`, `context`, `customColumnKeyValues`, `additionalMetadata`
  - Example count: 62 for history_guide

- **Conversational goldens**: `conversational_goldens.jsonl`
  - Format: JSONL with keys `scenario`, `userDescription`, `turns`, `customColumnKeyValues`
  - Example count: 20 for history_guide

### 2. Push to Confident AI

Use the `mcp0_push_dataset` MCP tool:

```python
# Single-turn dataset
mcp0_push_dataset(
    request={
        "alias": "ucore-history-guide-ollama-single-v1",
        "finalized": True,  # Important: set to True to commit goldens
        "goldens": [...]
    }
)

# Conversational dataset
mcp0_push_dataset(
    request={
        "alias": "ucore-history-guide-ollama-conversation-v1",
        "finalized": True,
        "conversationalGoldens": [...]
    }
)
```

**Critical Notes:**
- Always push with `finalized: true` to ensure goldens are committed
- Batch large datasets (10-20 goldens per batch) to avoid API payload issues
- Use consistent alias naming: `ucore-<npc>-<technique>-<type>-v1`

### 3. Verify Dataset Commitment

Pull the dataset to verify it's properly committed:

```python
mcp0_pull_dataset(request={"alias": "ucore-history-guide-ollama-single-v1"})
```

If successful, it returns the goldens. If empty, the push may have failed or not been finalized.

## Dataset Aliases

### history_guide
- Single-turn: `ucore-history-guide-ollama-single-v1` (62 goldens)
- Conversational: `ucore-history-guide-ollama-conversation-v1` (20 goldens)

### chef_assistant
- Single-turn: `ucore-chef-assistant-ollama-single-v1` (not yet pushed)
- Conversational: `ucore-chef-assistant-ollama-conversation-v1` (not yet pushed)

## Metric Collections

Confident AI provides pre-configured metric collections for NPC evaluation:

### npc-dataset-quality (Single-turn)
- **Answer Relevancy** (threshold: 0.8)
- **Faithfulness** (threshold: 0.8)
- **Hallucination** (threshold: 0.2)

### npc-conversation-quality (Multi-turn)
- **Role Adherence** (threshold: 0.8)
- **Knowledge Retention** (threshold: 0.8)
- **Conversation Completeness** (threshold: 0.8)

## AI Connection Setup (No-Code Evaluation)

AI Connections allow you to run evaluations directly on the Confident AI platform by connecting your AI app via an HTTPS endpoint. This eliminates the need to write evaluation code.

### 1. Start the NPC Server

Unsloth_Core includes a FastAPI server for serving NPC models:

```bash
# Activate environment
source unsloth_env/bin/activate

# Start the server
python src/npc_server/server.py
```

The server runs on `http://localhost:8000` and provides:
- `POST /generate` - Generate NPC response (generic)
- `POST /npc/{npc_key}/generate` - Generate response for specific NPC
- `GET /health` - Health check
- `GET /models` - List available models

### 2. Configure AI Connection in Confident AI

Navigate to: **Project Settings → AI Connections → New AI Connection**

**Basic Configuration:**
- **Name**: `unsloth-npc-server`
- **AI App Endpoint**: `https://your-domain.com/generate` (or `http://localhost:8000/generate` for local)
- **Streaming Mode**: HTTP Response (default)

**Payload Configuration (JSON mode):**
```json
{
  "input": golden.input,
  "context": golden.context,
  "hyperparameters": {
    "npc_key": "history_guide",
    "technique": "ollama"
  }
}
```

**Actual Output Key Path:**
The server returns `{"output": "...", "metadata": {...}}`, so set key path to: `output`

**Headers (if needed):**
```
Content-Type: application/json
```

**For Multi-turn Evaluations:**
```json
{
  "input": conversationalGolden.turns[-1].content,
  "context": conversationalGolden.context,
  "turns": conversationalGolden.turns,
  "hyperparameters": {
    "npc_key": "history_guide",
    "technique": "ollama"
  }
}
```

### 3. Run Evaluation via AI Connection

Once configured:
1. Go to your dataset in Confident AI
2. Click "Evaluate" → "AI Connection"
3. Select your AI connection (`unsloth-npc-server`)
4. Confident AI will call your endpoint with each golden and evaluate the response

### 4. Production Deployment

For production use, deploy the server with HTTPS:

```bash
# Using gunicorn with SSL
gunicorn -w 4 -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:443 \
  --certfile /path/to/cert.pem \
  --keyfile /path/to/key.pem \
  src.npc_server.server:app
```

Or use Docker:
```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY . .
RUN pip install fastapi uvicorn
CMD ["uvicorn", "src.npc_server.server:app", "--host", "0.0.0.0", "--port", "443"]
```

## Evaluation Workflow (Code-Based)

To run evaluations programmatically, you need actual model outputs. The workflow is:

### Option 1: Online Evaluation (mcp0_run_llm_evals)

Generate model outputs locally, then evaluate:

```python
# 1. Generate outputs using your model
test_cases = [
    {
        "input": "...",
        "actualOutput": "<model generated output>",
        "expectedOutput": "...",
        "context": [...]
    },
    ...
]

# 2. Run evaluation
mcp0_run_llm_evals(
    request={
        "metricCollection": "npc-dataset-quality",
        "llmTestCases": test_cases,
        "identifier": "history-guide-eval-v1"
    }
)
```

### Option 2: Trace-based Evaluation (mcp0_evaluate_trace)

If you have traces from actual model execution:

```python
mcp0_evaluate_trace(
    request={
        "metricCollection": "npc-dataset-quality",
        "overwriteMetrics": False
    },
    trace_uuid="<trace-uuid>"
)
```

### Option 3: Thread-based Evaluation (mcp0_evaluate_thread)

For multi-turn conversations:

```python
mcp0_evaluate_thread(
    request={
        "metricCollection": "npc-conversation-quality",
        "overwriteMetrics": False,
        "chatbotRole": "HistoryGuide"
    },
    thread_id="<thread-id>"
)
```

## Current Status

### Completed
- ✅ history_guide single-turn dataset pushed (62 goldens)
- ✅ history_guide conversational dataset pushed (20 goldens)
- ✅ Datasets verified and committed in Confident AI
- ✅ Metric collections identified

### Pending
- ⏳ Generate model outputs for evaluation
- ⏳ Run Confident AI evaluation on actual outputs
- ⏳ Push chef_assistant datasets
- ⏳ Integrate evaluation into ucore CLI

## Integration with ucore CLI

Future enhancement: Add Confident AI commands to ucore:

```bash
# Push datasets
./ucore confident push --npc history_guide --technique ollama

# Pull datasets
./ucore confident pull --alias ucore-history-guide-ollama-single-v1

# Run evaluation (requires model outputs)
./ucore confident evaluate --alias ucore-history-guide-ollama-single-v1 \
    --model-output-file outputs/history_guide_predictions.jsonl
```

## Confident AI Links

- Project: https://app.confident-ai.com/project/cmprumgxg002no313hqy1fqu4
- Single-turn dataset: https://app.confident-ai.com/project/cmprumgxg002no313hqy1fqu4/datasets/cmpyuz054001fqs13mrwh62lh
- Conversational dataset: https://app.confident-ai.com/project/cmprumgxg002no313hqy1fqu4/datasets/cmpyvd3ms000tl813gjo876q4

## Troubleshooting

### Dataset appears empty after push
- Ensure `finalized: true` is set during push
- Try pulling again after a few seconds (may need time to index)
- Check Confident AI UI to verify goldens appear

### Evaluation fails without actual outputs
- Evaluation requires `actualOutput` field in test cases
- Generate outputs using your trained model first
- Use `mcp0_run_llm_evals` for batch evaluation of local predictions

### Batch size issues
- Keep batches to 10-20 goldens per push
- Split large datasets into multiple pushes with same alias
- All pushes to same alias will be merged
