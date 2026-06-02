# Confident AI Connections + Classifiers recommendation

Date: 2026-06-02
Scope: Improve Unsloth_Core NPC dataset generation, DeepEval/Confident eval feedback, and LoRA/runtime diagnosis.

## Docs checked

- https://www.confident-ai.com/docs/settings/project/classifiers
- https://www.confident-ai.com/docs/settings/project/ai-connections
- https://www.confident-ai.com/docs/settings/project/confident-agent
- https://www.confident-ai.com/docs/settings/project/transformers

## Current local signals checked

chef_assistant / ollama:

- quality_summary: pass_rate 1.0 on fast smoke, 5/5 categories passed.
- sanitizer mean 80.9, min 77, no flagged rows.
- distribution gaps: none.
- Confident golden projection: 70 single-turn, 2 conversational.

history_guide / ollama:

- quality_summary: pass_rate 0.8 on fast smoke, 4/5 passed.
- failed category: dialogue.
- distribution gaps: dialogue shortfall 1, refusal shortfall 6.
- main failure: vague classical antiquity answer, low specificity/usefulness score 0.2 and persona/category score 0.7.
- Confident golden projection: 65 single-turn, 0 conversational.

## Decision

We should configure Classifiers now.

We should configure AI Connections after we expose a local HTTPS/runtime endpoint or run Confident Agent. AI Connections are valuable, but they require Confident AI to call an HTTPS endpoint that returns actual model output. Our current pipeline can already run local code-driven evals, so AI Connection is not a blocker for dataset iteration. It becomes important when we want platform-click evals against Unity/base+LoRA/runtime memory.

## AI Connection recommendation

### When to set it

Set up an AI Connection when one of these is true:

1. We want Confident UI to run evals from uploaded goldens without local CLI.
2. We want to evaluate the actual NPC runtime endpoint, not just local test code.
3. We want multi-turn Confident simulations to persist state across turns.
4. We want traces linked to test cases/turns in Observatory.

### Required execution shape

Confident AI needs:

- HTTPS POST endpoint.
- Endpoint returns JSON with actual output.
- Auth header/secrets configured in Confident.
- Actual Output Key Path configured.
- For multi-turn: state input/output mapping.
- For trace linking: testCaseId and turnId passed through endpoint/tracing.

If endpoint is local/private, use Confident Agent:

- Runs locally or in Docker.
- Connects outbound WSS/443 to Confident.
- No inbound port needed.
- Requires CONFIDENT_API_KEY.

### Recommended AI Connections

#### 1. `ucore-local-npc-single`

Purpose: single-turn evals against our local NPC inference/eval endpoint.

Mode:

- HTTP Response.

Payload JSON:

```json
{
  "npc_key": golden.additional_metadata.npc_key,
  "input": golden.input,
  "context": golden.context,
  "expected_output": golden.expected_output,
  "system_prompt_hash": golden.additional_metadata.system_prompt_hash,
  "reference_doc_hash": golden.additional_metadata.reference_doc_hash,
  "test_case_id": testCaseId,
  "hyperparameters": hyperparameters
}
```

Response contract:

```json
{
  "actual_output": "NPC response text",
  "retrieval_context": ["optional chunks"],
  "metadata": {
    "npc_key": "chef_assistant",
    "model": "...",
    "adapter": "..."
  }
}
```

Key paths:

- Actual Output Key Path: `["actual_output"]`
- Retrieval Context Key Path: `["retrieval_context"]` only if endpoint returns it.

Recommended parameters:

- Request timeout: 60s for local 3B CPU/GPU eval; 120s if Unity/runtime bridge is slow.
- Max concurrency: 1-2 on RTX 3060-class 6GB VRAM.
- Hyperparameters:
  - npc_key
  - technique
  - dataset_sha
  - spec_sha
  - refdoc_sha
  - base_model
  - lora_run_id
  - prompt_version
  - temperature
  - max_tokens
  - runtime

#### 2. `ucore-local-npc-conversation`

Purpose: multi-turn memory/Knowledge Retention evals.

Payload JSON:

```json
{
  "npc_key": conversationalGolden.additional_metadata.npc_key,
  "scenario": conversationalGolden.scenario,
  "user_description": conversationalGolden.user_description,
  "expected_outcome": conversationalGolden.expected_outcome,
  "turns": conversationalGolden.turns,
  "context": conversationalGolden.context,
  "state": state,
  "turn_id": turnId,
  "test_case_id": testCaseId,
  "hyperparameters": hyperparameters
}
```

Response contract:

```json
{
  "actual_output": "NPC response text",
  "state": {
    "thread_id": "...",
    "remembered_facts": []
  }
}
```

Key paths:

- Actual Output Key Path: `["actual_output"]`
- State Key Path: `["state"]`

Recommended parameters:

- Request timeout: 90-120s.
- Max concurrency: 1 for stateful local runtime.
- Must pass/return state so Confident can keep memory across turns.

## Classifier recommendation

Confident classifiers tag traces/threads as Signals. They are LLM-driven. No regex, no metadata prefilter. Descriptions must be specific.

Classifiers require Premium plan or above.

### Sampling

Development / low-volume evals:

- Trace sample rate: 1.0
- Thread sample rate: 1.0

Production / high-volume runtime:

- Start 0.25-0.5
- Increase to 1.0 only during diagnosis windows.

### Trace Classifiers

#### 1. `NPC Dataset Failure Mode`

Description:

Classify why an NPC response or generated dataset row is weak. Use the input, output, metadata, and metric reasons. Choose the most important failure mode. Return no label if the row is strong and no failure is visible.

Labels:

- `Vague / Low Specificity`
  - Label when the answer is generic, lacks concrete facts/examples, or does not teach enough to be useful for SFT.
  - Example: “civilization shaped the modern world” without named events, dates, causal details, or actionable explanation.

- `Role Drift`
  - Label when the NPC stops sounding like its role/persona, speaks as a generic assistant, or ignores persona/style constraints.

- `Constraint Violation`
  - Label when the response violates max sentence/character/format rules, uses disallowed markdown, or ignores runtime style constraints.

- `Grounding Gap / Possible Hallucination`
  - Label when the answer makes factual claims not supported by the reference context or seems historically/culinarily unsafe or unsupported.

- `Weak User-Question Fit`
  - Label when the response does not directly answer the user’s question or misses the requested task.

- `Safety Boundary Weakness`
  - Label when refusal/safety handling is missing, unsafe, over-refuses, or fails to redirect safely.

Recommended use:

- Dashboard by npc_key/category/concept/difficulty.
- Repair generation prompts by dominant failure mode.

#### 2. `NPC Dataset Strength`

Description:

Classify the main strength of a strong NPC response or dataset row. Choose one label only when the strength is clearly present.

Labels:

- `Concrete Teaching`
  - Gives useful facts, examples, steps, dates, temperatures, concepts, or causal explanation.

- `Strong Persona Fit`
  - Clearly matches NPC identity, tone, and role while still answering naturally.

- `Good Refusal / Safe Redirect`
  - Sets a safe boundary and redirects to helpful allowed guidance.

- `Good Runtime Fit`
  - Short, natural, follows sentence/format limits, and would fit Unity dialogue.

- `Good Memory Use`
  - Correctly uses a prior user fact/preference/constraint in a later response.

Recommended use:

- Mine strong rows as exemplars for regeneration prompts and reference docs.

#### 3. `NPC Repair Priority`

Description:

Classify how urgently a trace/dataset row needs repair for production SFT quality.

Labels:

- `P0 Safety/Factual Risk`
  - Unsafe, misinformation, harmful refusal failure, or severe hallucination.

- `P1 Training Harmful`
  - Would teach the model bad behavior: vague, wrong style, wrong role, or poor answer fit.

- `P2 Improve Later`
  - Usable but could be more specific, balanced, or better phrased.

- `No Repair Needed`
  - Strong enough for current dataset goals.

Recommended use:

- Filter repair queues.
- Only P0/P1 should block production training.

### Thread Classifiers

#### 1. `NPC Conversation Outcome`

Description:

Classify the outcome of a multi-turn NPC conversation after the thread is idle. Focus on whether the NPC fulfilled the player’s goal while preserving role, safety, and memory.

Labels:

- `Resolved Helpful`
  - User goal is answered or completed clearly.

- `Unresolved / User Still Confused`
  - User repeats the question, expresses confusion, or the conversation ends without a useful answer.

- `Memory Retained`
  - NPC correctly uses prior user facts/preferences/constraints later in the conversation.

- `Memory Lost`
  - NPC ignores or contradicts a prior user fact/preference/constraint.

- `Escalated Safety Boundary`
  - Conversation required refusal/safety redirect and the NPC handled it.

#### 2. `NPC User Sentiment`

Description:

Classify the user’s apparent sentiment across a conversation. Use only explicit user language, not the model’s confidence.

Labels:

- `Positive / Satisfied`
- `Neutral`
- `Confused`
- `Frustrated`
- `Concerned About Safety`

#### 3. `NPC Conversation Weakness`

Description:

Classify the main conversation-level weakness. Return no label if no weakness is visible.

Labels:

- `Lost Context`
- `Too Generic`
- `Too Long / Not Game-Ready`
- `Unsafe or Unverified Advice`
- `Role Inconsistent`
- `Did Not Complete Task`

## Classifiers mapped to current weaknesses

history_guide:

- Need `NPC Dataset Failure Mode` now.
- Expected labels from current failure:
  - `Vague / Low Specificity`
  - maybe `Weak User-Question Fit`
- Need generation repair focused on dialogue/classical antiquity concrete details.
- Need more refusal rows: current 2 vs target 8.
- Need conversational goldens: current 0.

chef_assistant:

- Current fast smoke is strong.
- Need `NPC Dataset Strength` to mine good examples.
- Need more conversational/memory goldens: current 2 is too low for Knowledge Retention mastery.
- Safety classifier useful because cooking/food safety failures are high-risk.

## Implementation changes recommended in repo

1. Add classifier labels to Confident golden custom columns when known locally:

```json
"customColumnKeyValues": {
  "npc_key": "history_guide",
  "category": "dialogue",
  "concept": "classical antiquity",
  "difficulty": "beginner",
  "turn_type": "single",
  "quality_status": "candidate",
  "repair_priority": "P1 Training Harmful",
  "expected_failure_mode": "Vague / Low Specificity"
}
```

2. Add classifier guidance to reference docs:

- Good answer traits.
- Bad answer traits.
- Failure mode examples.
- Strength examples.

3. Add runtime endpoint before AI Connection:

- `/eval/single`
- `/eval/conversation`

4. Add trace linkage fields:

- `testCaseId`
- `turnId`

5. Add hyperparameters to every run:

- npc_key
- technique
- dataset_sha
- spec_sha
- refdoc_sha
- generator_model
- judge_model
- base_model
- lora_run_id
- prompt_version
- temperature
- max_tokens

## Exact next action

P0:

1. Create Confident classifiers in UI:
   - `NPC Dataset Failure Mode`
   - `NPC Dataset Strength`
   - `NPC Repair Priority`
2. Set trace sample rate to `1.0` for current low-volume evals.
3. Leave AI Connection pending unless we expose an HTTPS endpoint or run Confident Agent.

P1:

1. Build local HTTPS/runtime eval endpoint.
2. Run Confident Agent if endpoint stays local/private.
3. Create AI Connections:
   - `ucore-local-npc-single`
   - `ucore-local-npc-conversation`
4. Set max concurrency to 1-2 for local 6GB VRAM.
5. Add state key path for multi-turn eval.

P2:

1. Add Thread Classifiers after runtime tracing/multi-turn thread ingestion works.
2. Use thread classifiers for Memory Retained/Lost and User Sentiment dashboards.
