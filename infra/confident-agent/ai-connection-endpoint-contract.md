# Future Confident AI Connection endpoint contract

Status: planned. Do not enable Confident Agent until these endpoints exist.

## `ucore-local-npc-single`

Endpoint:

```text
POST /eval/single
```

Request body from Confident AI Connection:

```json
{
  "npc_key": "golden.additional_metadata.npc_key",
  "input": "golden.input",
  "context": "golden.context",
  "expected_output": "golden.expected_output",
  "test_case_id": "testCaseId",
  "hyperparameters": "hyperparameters"
}
```

Response body:

```json
{
  "actual_output": "NPC response text",
  "retrieval_context": [],
  "metadata": {
    "npc_key": "history_guide",
    "model": "base model id/path",
    "adapter": "adapter id/path"
  }
}
```

Confident key paths:

- Actual Output Key Path: `["actual_output"]`
- Retrieval Context Key Path: `["retrieval_context"]` if returned.

## `ucore-local-npc-conversation`

Endpoint:

```text
POST /eval/conversation
```

Request body:

```json
{
  "npc_key": "conversationalGolden.additional_metadata.npc_key",
  "scenario": "conversationalGolden.scenario",
  "expected_outcome": "conversationalGolden.expected_outcome",
  "turns": "conversationalGolden.turns",
  "state": "state",
  "turn_id": "turnId",
  "test_case_id": "testCaseId",
  "hyperparameters": "hyperparameters"
}
```

Response body:

```json
{
  "actual_output": "NPC response text",
  "state": {
    "thread_id": "stable conversation id",
    "remembered_facts": []
  }
}
```

Confident key paths:

- Actual Output Key Path: `["actual_output"]`
- State Key Path: `["state"]`

## Local resource parameters

- Single-turn timeout: 60s.
- Conversation timeout: 90-120s.
- Max concurrency: 1 for stateful local runtime, 1-2 for stateless local 3B eval.
