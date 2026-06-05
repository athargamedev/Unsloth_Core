# Confident AI dataset/eval best-practices audit

Date: 2026-06-02
Scope: Unsloth_Core NPC reference docs, dataset JSONL, Confident dataset push, remote eval metric collections, and DeepEval training/eval workflow.

## Confident/DeepEval facts that change our design

Sources read:

- https://www.confident-ai.com/docs/api-reference/datasets/push-dataset.mdx
- https://www.confident-ai.com/docs/llm-evaluation/core-concepts/test-cases-goldens-datasets
- https://www.confident-ai.com/docs/llm-evaluation/dataset-management/automate-dataset-management
- https://www.confident-ai.com/docs/llm-evaluation/dataset-management/using-datasets.mdx
- https://www.confident-ai.com/docs/metrics/metric-collections
- https://www.confident-ai.com/docs/api-reference/evaluation/evaluate-llm

Key rules:

1. Confident datasets contain goldens, not already-evaluated training rows.
2. A dataset is single-turn or multi-turn; do not mix both in one Confident dataset.
3. Single-turn dataset push uses `goldens`.
4. Multi-turn dataset push uses `conversationalGoldens`.
5. `finalized=true` makes goldens available for evaluation; `finalized=false` queues them for review.
6. Only finalized goldens are pulled by default.
7. Do not pre-populate golden fields that should come from runtime evaluation:
   - single-turn goldens: avoid `actualOutput`, `retrievalContext`, `toolsCalled` unless intentionally storing executed examples.
   - conversational goldens: avoid full `turns` except optional opening turns; prefer `scenario` + runtime simulation for real multi-turn eval.
8. Test cases are produced at eval time from goldens + actual app/model output.
9. Calling `dataset.add_test_case(test_case)` is important in code-driven DeepEval because it links test runs back to datasets for regression comparison.
10. Remote `/v1/evaluate` expects `metricCollection` as a collection name string.
11. Remote metric collections are managed by project and should be named/stable.
12. Use `customColumnKeyValues` for searchable/editable metadata columns.
13. Use `additionalMetadata` for richer machine metadata/provenance.
14. Log hyperparameters on eval runs so Confident can compare prompts/models retrospectively.

## Current repo state observed

Dataset row format currently used for training:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "metadata": {
    "npc_key": "chef_assistant",
    "category": "quest",
    "technique": "ollama",
    "source": "ollama:OllamaGenerator",
    "split": "train",
    "concept": "food safety",
    "difficulty": "intermediate",
    "generator_params": {
      "seed": 42,
      "temperature": 0.6,
      "multi_turn": false,
      "reference_doc": "data/npcs/reference_docs/chef_assistant_primer.md"
    },
    "content_hash": "..."
  }
}
```

Observed counts:

- chef_assistant / ollama: 72 rows, 70 single-turn, 2 multi-turn.
- history_guide / ollama: 65 rows, 65 single-turn, 0 multi-turn.
- Metadata keys already useful: npc_key, category, technique, source, split, concept, difficulty, safety_tags, generator_params, content_hash, boundary, dialogue_type, scenario_name.

Current issues:

1. Training JSONL rows are being treated too directly as Confident goldens.
2. Rows include assistant outputs, which are useful for SFT but are not ideal as Confident goldens unless mapped intentionally to `expectedOutput`, not `actualOutput`.
3. Single-turn and multi-turn examples currently live together in one local train file.
4. Confident dataset push client only supports `goldens`; it does not support `conversationalGoldens` yet.
5. Confident push client has no explicit `finalized=false` review mode in CLI flow.
6. Dataset aliases/versioning are not yet standardized around npc, technique, split, turn type, and dataset hash.
7. Reference docs are grounded primers but are not represented as Confident `context` chunks/sourceFile metadata for each golden.
8. DeepEval test path evaluates local train rows directly, not by pulling Confident datasets and adding test cases back to the dataset object.
9. Hyperparameter logging is incomplete; DeepEval warns “No hyperparameters logged.”
10. Multi-turn memory-retention goldens are too few for learning/mastery.
11. Metrics should be separated by purpose: dataset generation quality, SFT output quality, runtime Unity/NPC quality, memory-retention quality.

## Required structure changes

### 1. Keep training rows, but add Confident goldens as first-class artifacts

Do not replace ChatML training files. Add Confident-native projections beside them:

```text
data/datasets/<npc>/<technique>/
  train.jsonl                 # raw/generated ChatML for SFT
  train_clean.jsonl           # sanitized ChatML for SFT
  validation.jsonl            # optional local validation ChatML
  train_manifest.json         # provenance/quality summary
  confident/
    single_turn_goldens.jsonl
    conversational_goldens.jsonl
    push_manifest.json
    pull_check.json
```

Why:

- ChatML is best for training.
- Confident goldens are best for dataset review, eval linkage, regression, custom columns, and remote metric collections.

### 2. Single-turn golden projection format

For each 3-message ChatML row:

```json
{
  "input": "last user message only",
  "expectedOutput": "assistant answer from training row",
  "context": ["short relevant reference-doc snippets or contract text"],
  "comments": "Generated from train_clean.jsonl; review before finalizing if not approved.",
  "sourceFile": "data/datasets/<npc>/<technique>/train_clean.jsonl",
  "additionalMetadata": {
    "npc_key": "chef_assistant",
    "technique": "ollama",
    "content_hash": "...",
    "system_prompt_hash": "...",
    "reference_doc": "data/npcs/reference_docs/chef_assistant_primer.md",
    "reference_doc_hash": "...",
    "generator": "ollama:OllamaGenerator",
    "generator_params": {...},
    "split": "train"
  },
  "customColumnKeyValues": {
    "npc_key": "chef_assistant",
    "category": "quest",
    "concept": "food safety",
    "difficulty": "intermediate",
    "technique": "ollama",
    "source": "ollama",
    "split": "train",
    "turn_type": "single",
    "quality_status": "candidate"
  }
}
```

Important:

- Do not use `actualOutput` for generated training data; use `expectedOutput` if the row is approved as ideal behavior.
- Use `input` as user content, not the whole system prompt.
- Put system prompt / persona contract in metadata/context, not in input.
- Put searchable tags in `customColumnKeyValues`.
- Put larger provenance objects in `additionalMetadata`.

### 3. Conversational golden projection format

For multi-turn/memory rows, project to `conversationalGoldens`:

```json
{
  "scenario": "User tells ChefAssistant a dietary preference/allergy, then asks a later cooking question where the assistant must remember it.",
  "userDescription": "Home cook or apprentice; may state preferences, restrictions, or goals.",
  "expectedOutcome": "Assistant acknowledges and uses the remembered user-provided fact in later turns while staying in ChefAssistant role.",
  "context": ["NPC role contract", "relevant memory-retention rule", "reference snippets"],
  "turns": [
    {"role": "user", "content": "Remember that I am allergic to peanuts."}
  ],
  "comments": "Opening turn only; full conversation should be generated/evaluated at runtime when possible.",
  "sourceFile": "data/datasets/<npc>/<technique>/train_clean.jsonl",
  "additionalMetadata": {
    "npc_key": "chef_assistant",
    "memory_fact_type": "allergy",
    "memory_retention_target": "user-provided facts across turns",
    "content_hash": "..."
  },
  "customColumnKeyValues": {
    "npc_key": "chef_assistant",
    "category": "dialogue",
    "concept": "memory retention",
    "difficulty": "intermediate",
    "turn_type": "multi",
    "metric_focus": "knowledge_retention"
  }
}
```

Important:

- Confident says multi-turn datasets should be separate from single-turn datasets.
- For memory-retention mastery, prefer scenarios + expected outcomes, and let the eval harness/runtime model generate turns.
- Keep optional seed/opening turns only when needed.

### 4. Dataset aliases and versioning

Use stable aliases:

```text
ucore-<npc>-<technique>-single-v1
ucore-<npc>-<technique>-conversation-v1
```

Examples:

```text
ucore-chef-assistant-ollama-single-v1
ucore-chef-assistant-ollama-conversation-v1
ucore-history-guide-ollama-single-v1
ucore-history-guide-ollama-conversation-v1
```

Use `version` or push manifest values:

```text
<YYYYMMDD>-<train_clean_sha8>-<spec_sha8>-<refdoc_sha8>
```

Push modes:

- `finalized=false`: newly generated/candidate rows, before human or quality review.
- `finalized=true`: approved eval-ready goldens only.

### 5. Reference doc structure changes

Current reference docs pass a simple generation contract. For Confident best practice, add machine-usable sections that can become golden `context` and custom columns:

```markdown
# <NPC> Reference Primer

## Evaluation Contract
- Role:
- Allowed domain:
- Forbidden domain:
- Refusal policy:
- Style constraints:
- Runtime constraints:

## Concepts
### <concept name>
- Difficulty:
- Category:
- Canonical facts:
- Common misconceptions:
- Good answer traits:
- Bad answer traits:

## Memory Retention Scenarios
- User fact type:
- Opening user fact:
- Later user request:
- Expected remembered behavior:
- Failure modes:

## Source Snippets
- Snippet ID:
- Text:
- Applies to concepts:
```

Why:

- Confident goldens have `context` and `sourceFile`; our reference docs should provide short retrievable chunks.
- Metrics like Faithfulness/Contextual Relevancy work better when static context is explicit.
- Memory-retention goldens need expected outcomes/failure modes.

### 6. Spec changes

Add an optional `confident` block to each NPC spec:

```json
"confident": {
  "dataset_alias_prefix": "ucore-chef-assistant-ollama",
  "single_turn_collection": "npc-dataset-quality",
  "conversation_collection": "npc-conversation-quality",
  "push_default_finalized": false,
  "custom_columns": [
    "npc_key", "category", "concept", "difficulty", "technique", "source",
    "split", "turn_type", "metric_focus", "quality_status"
  ],
  "memory_retention": {
    "minimum_goldens": 20,
    "fact_types": ["preference", "allergy", "skill_level", "goal", "constraint"]
  }
}
```

Also add `evaluation_contract` or `golden_contract` fields:

```json
"evaluation_contract": {
  "input_mapping": "last_user_message",
  "expected_output_mapping": "assistant_message_for_approved_rows",
  "context_sources": ["reference_doc", "system_prompt_rules"],
  "runtime_output_required": true
}
```

### 7. Metrics and metric collections

Keep current remote collections but split by workflow:

#### Dataset generation / single-turn collection

Name: `npc-dataset-quality`

Recommended metrics/settings:

- Answer Relevancy, threshold 0.8
- Faithfulness, threshold 0.8
- Hallucination, threshold strict/low tolerated risk
- Bias/Toxicity if available for safety-sensitive categories

Purpose:

- Validate generated row quality and groundedness.

#### Conversation / memory collection

Name: `npc-conversation-quality`

Recommended metrics/settings:

- Role Adherence, threshold 0.8
- Knowledge Retention, threshold 0.8
- Conversation Completeness, threshold 0.8
- Turn Relevancy if available

Purpose:

- Validate user-provided fact retention and multi-turn NPC continuity.

#### Runtime Unity / production eval collection

Name: `npc-runtime-quality`

Recommended metrics/settings:

- Task Completion / Conversation Completeness
- Role Adherence
- Safety/refusal custom GEval/DAG metric locally
- Knowledge Retention for dialogue sessions with local Supabase memory

Purpose:

- Evaluate base+LoRA runtime behavior, not just dataset examples.

#### Component-level tracing collection

Name: `npc-component-quality`

Recommended components:

- spec_parser
- reference_retriever
- generator
- sanitizer
- judge_runner
- unity_runtime_adapter
- memory_store

Purpose:

- Use Confident tracing/observe flows to identify component root causes.

### 8. Parameters/hyperparameters to log

Every DeepEval/Confident run should log:

```json
{
  "NPC": "chef_assistant",
  "Technique": "ollama",
  "Dataset SHA": "...",
  "Spec SHA": "...",
  "Reference Doc SHA": "...",
  "Generator": "ollama",
  "Generator Model": "...",
  "Generator Temperature": 0.6,
  "Generator Seed": 42,
  "Judge Model": "qwen2.5:7b",
  "Base Model": "llama3.2-3b",
  "LoRA Run ID": "...",
  "Prompt Version": "...",
  "Sanitizer Version": "...",
  "Quality Gate Mode": "fast|release"
}
```

Why:

- Confident best practice says hyperparameters let you compare prompts/models retrospectively.
- We currently get DeepEval warning: “No hyperparameters logged.”

## Required code changes

1. Add `src/core/dataset/confident_goldens.py`
   - Convert ChatML rows to Confident `Golden` and `ConversationalGolden` payloads.
   - Split single/multi turn.
   - Add `customColumnKeyValues`, `additionalMetadata`, `sourceFile`, `comments`, `context`.
   - Avoid `actualOutput`; use `expectedOutput` only for approved rows.

2. Extend `ConfidentAPIClient.push_dataset()`
   - Accept `conversational_goldens`.
   - Send exactly one of `goldens` or `conversationalGoldens`.
   - Preserve `finalized`.
   - Capture returned dataset `link`.

3. Extend `confident_push.py` CLI
   - `push-single` / `push-conversation` or `--turn-type single|conversation`.
   - `--finalized/--unfinalized`.
   - `--alias` default from npc/technique/turn type.
   - `--version` default from content/spec/refdoc hashes.

4. Add dataset projection command to `./ucore`
   - Example:
     ```bash
     ./ucore confident-goldens data/npcs/specs/chef_assistant.json --technique ollama --finalized false --push
     ```

5. Add pull-based eval path
   - Pull Confident dataset by alias.
   - Invoke model/app for each golden.
   - Construct DeepEval test cases.
   - Call `dataset.add_test_case(test_case)` before evaluate/assert_test.
   - This links test run to dataset.

6. Add hyperparameter logging
   - For `deepeval test run`, use `@deepeval.log_hyperparameters()` or equivalent test-run hook.
   - For remote `/v1/evaluate`, populate `hyperparameters` in request body.

7. Add minimum memory-retention dataset rule
   - Per active NPC: at least 20 conversational goldens before production runtime eval.
   - Fact types: preference, allergy/safety constraint, learning goal, prior error, ingredient/tool constraint.

8. Update validation
   - Validate Confident golden projections separately from train JSONL.
   - Validate no mixed single/conversation Confident dataset pushes.
   - Validate required custom columns.
   - Validate finalized push only from approved/sanitized rows.

## Priority implementation order

### P0 - must do now

1. Add Confident golden projection files under `data/datasets/<npc>/<technique>/confident/`.
2. Split single-turn and conversational goldens.
3. Extend push API/client for `conversationalGoldens`.
4. Add `finalized=false` review mode.
5. Add run hyperparameters for local DeepEval and remote Confident eval.

### P1 - next

1. Add pull-based dataset eval that uses `EvaluationDataset.pull()` + `dataset.add_test_case()`.
2. Add reference-doc chunk/context extraction for goldens.
3. Add 20+ memory-retention conversational goldens per active NPC.
4. Add spec `confident` blocks.

### P2 - later

1. Add component-level tracing around generation/sanitization/judge/runtime.
2. Add Confident dataset review workflow and promotion from unfinalized to finalized.
3. Add prompt/model versioning integration.

## Bottom line

We should stop treating ChatML SFT rows as the same object as Confident goldens.

Keep:

- ChatML JSONL for training.

Add:

- Confident single-turn goldens for dataset review/regression.
- Confident conversational goldens for Knowledge Retention/memory continuity.
- Pull-based DeepEval flow that links test runs to datasets.
- Hyperparameters on every run.
- Reference docs formatted to provide context snippets and evaluation contracts.
