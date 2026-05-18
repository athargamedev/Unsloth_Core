# Improved Dataset Generation Workflow
> **Design Document** — A modular, provenance-tracked pipeline from reference docs to production-ready ChatML datasets for SFT, RL, eval, and feedback loops.

## Design Principles

1. **Provenance is law** — Every example carries its full origin chain: technique, source, seed, generator params, sanitizer version, content hash.
2. **Metadata completeness** — Every example MUST populate ALL schema-supported metadata fields. Incomplete metadata = failed validation.
3. **Grounding in reference docs** — All LLM-generated content must be traceable to reference documents or structured expertise lists.
4. **Stratified by design** — Datasets are balanced by category, concept, difficulty, and safety tags at generation time, not post-hoc.
5. **RL-readiness from day one** — Every NPC spec carries the structure needed to generate preference pairs and reward rollouts, not just SFT examples.
6. **Feedback loop closure** — Eval results map directly to regeneratable dataset patches with no reverse-engineering.

## Current Gaps (Why This Workflow Exists)

| Gap | Impact | Fix |
|-----|--------|-----|
| Template generics produce samey NPC responses | Training data lacks personality; models learn generic patterns | Spec-aware template assembly with NPC traits, subject, and reference doc snippets |
| No difficulty tagging | Eval sets can't stratify by difficulty; can't measure model depth | Every example tagged beginner/intermediate/advanced via spec rules |
| No safety_tags on refusal examples | RL safety tuning has no signal | Refusal examples tagged with boundary violation type |
| No concept metadata on identity/refusal examples | Feedback loop can't identify weak persona or refusal areas | All categories get concept labels |
| No reference doc grounding | LLM-generated data drifts from factual sources | Generation prompts include reference doc snippets as grounding |
| RL schemas exist but no generation pipeline | Cannot generate RLHF training data | Separate RL pipeline with preference pairs, reward rollouts |
| Sanitizer is minimal | AI artifacts slip through, no quality scoring | Multi-stage sanitizer with quality scoring rubric |
| No content hashing | Can't detect duplicate or drifted examples | SHA256 content hash per example |
| Feedback loop is shallow (win rate only) | Misses semantic gaps, concept-specific issues | Concept-level gap analysis with actionable recommendations |
| No dataset manifest | No versioning, no reproducibility | Per-generation manifest JSON with full provenance |

## Pipeline Architecture

```
[Phase 0]  Subject Spec + Reference Docs
                 │
                 ▼
[Phase 1]  Structured Dataset Generation
            ├── 1a: Spec-Aware Concept Extraction
            ├── 1b: Category Generation (template or LLM)
            └── 1c: Reference-Doc-Grounded Answers
                 │
                 ▼
[Phase 2]  Quality Sanitization & Enrichment
            ├── 2a: Structural Validation
            ├── 2b: AI Artifact Filtering
            ├── 2c: Quality Scoring
            └── 2d: Metadata Enrichment
                 │
                 ▼
[Phase 3]  Dataset Provenance & Manifest
            ├── 3a: Content Hashing
            └── 3b: Manifest Generation
                 │
                 ├──────────────────────────────────┐
                 ▼                                  ▼
          [Training Pipeline]              [RL Dataset Generation]
                                            ├── 4a: Preference Pairs
                                            ├── 4b: Reward Rollouts
                                            └── 4c: Comparative Examples
                                                    │
                                                    ▼
                                           [Feedback Loop Integration]
                                            ├── 5a: Eval Dataset Curation
                                            ├── 5b: Concept Gap Analysis
                                            └── 5c: Targeted Regeneration
```

---

## Phase 0: Subject Spec & Reference Doc Preparation

### Inputs
- NPC concept, domain description
- Domain reference materials

### Outputs
- `subjects/{npc_key}.json` — validated subject spec
- `subjects/reference_docs/{npc_key}_primer.md` — structured primer
- (Optional) `docs/corpora/{npc_key}_manifest.json` — corpus manifest for multi-source grounding

### Validation Gates

**Subject Spec Validation (`validate_subject_spec.py`):**
- REQUIRED: npc_key (snake_case), npc_name, subject, identity.{personality,background,mannerisms}
- REQUIRED: teaching.{expertise (non-empty list), approach, difficulty_levels}
- REQUIRED: dialogue.{conversation_style, max_sentences (1-5), example_topics (≥4)}
- REQUIRED: quest.scenarios (≥1 named scenario with description)
- REQUIRED: refusal.{boundaries (≥2), redirect_policy}
- REQUIRED: system_prompt (4-section IDENTITY|VOICE|KNOWLEDGE|RULES format)
- REQUIRED: dataset.examples_per_category with ALL 5 categories present
- OPTIONAL but RECOMMENDED: reference_doc pointing to primer
- STRICT: system_prompt must mention max_sentences constraint
- STRICT: All 5 categories must be present in examples_per_category
- WARNING: If max_sentences > 3 for dialogue category

**Reference Doc Requirements:**
- MUST start with a `# {NPC_Name} Primer` heading
- MUST use `##` markdown section headers for major topics
- Each section should be 3-8 bullet points of concise facts
- MUST NOT contain conversational or instructional prose (primers are fact banks)
- MUST be ≤ 5KB for efficient LLM context window usage

**Schema File:** `subjects/schemas/sft_record.schema.json` (see Appendix A)

---

## Phase 1: Structured Dataset Generation

### 1a: Spec-Aware Concept Extraction

**Input:** Subject spec JSON
**Output:** Structured concept pool with difficulty levels

**Algorithm (replaces current `concept_pool_for_subject()`):**

```
1. Extract concepts from teaching.expertise (primary source)
2. Extract phrases from subject description
3. Extract concepts from research_queries (noun-phrase filtered)
4. Extract concepts from reference_doc sections (heading-derived)
5. For each concept, infer difficulty:
   - If concept appears in teaching.difficulty_levels, use that
   - Otherwise, heuristic: short concepts (1-2 words) = "beginner",
     compound concepts = "intermediate", specialized = "advanced"
   - Overridable via spec-level mapping
6. Deduplicate with canonical form (lowercase, stripped)
7. Return: [{name, difficulty, source (expertise/subject/doc)}]
```

### 1b: Category-Specific Generation with Full Metadata

**Input:** Subject spec + concept pool
**Output:** ChatML JSONL examples with complete metadata

**Per-category generation rules:**

#### identity (12 examples)
- User prompts derived from personality + background (not generic "Who are you?")
- Assistant responses incorporate NPC mannerisms
- **Concept:** `npc_key`
- **Metadata:** category=identity, concept=npc_key, difficulty=beginner

**Example user:** "I heard you're the one who makes history come alive. Is that true?"
**Example assistant:** "That's me! HistoryGuide at your service. I love connecting the dots between past events and the world you see today. Ask me anything about ancient civilizations—you might be surprised how relevant they still are!"

#### teaching (56 examples)
- 40% beginner concepts, 35% intermediate, 25% advanced (configurable)
- Each example references at least one concept
- User prompts should reflect realistic learner questions
- Assistant responses must include 1 analogy or real-world connection
- **Metadata:** category=teaching, concept=<name>, difficulty=<level>, related_concepts=[]

#### dialogue (32 examples)
- Follow-up questions that build on prior knowledge
- Require assistant to connect back to previously discussed concepts
- 20% should be clarification requests, 30% deeper-dive questions, 30% application questions, 20% misconception probes
- **Metadata:** category=dialogue, concept=<name>, difficulty=<level>, dialogue_type=clarification|deep_dive|application|misconception

#### quest (16 examples)
- Scenario-based challenges from quest.scenarios
- Must match scenario name from spec
- User prompt describes real-world application context
- Assistant response provides structured challenge (question + hint + success criteria)
- **Metadata:** category=quest, concept=<name>, difficulty=<level>, scenario=<name>

#### refusal (16 examples)
- Derived directly from refusal.boundaries
- Each boundary gets (total_boundaries ÷ count) examples
- User prompts should be realistic, not cartoonishly off-topic
- Assistant responses follow redirect_policy exactly
- **Metadata:** category=refusal, concept=<boundary>, difficulty=beginner, safety_tags=[boundary_category]

### 1c: Reference-Doc-Grounded Generation

**When using LLM generation (Ollama/OpenAI/Anthropic):**

Every generation prompt must include:
1. The full system prompt from spec
2. Relevant reference_doc sections (filtered by concept match)
3. Specific format guidance per category (from 1b rules)
4. A sentence budget: "Keep assistant responses to {max_sentences} sentences"

**Prompt template structure:**

```
SYSTEM: You are a synthetic data generator for NPC training.
Ground your answers in the following reference material only.

REFERENCE DOCUMENT:
{doc_sections}

NPC SYSTEM PROMPT: {system_prompt}

TASK: Generate a {category} example about "{concept}".
Difficulty level: {difficulty}

{category_specific_instructions}

Return valid JSON with:
- user: realistic {category} question
- assistant: in-character response ({max_sentences} sentences max)
- thought: how this follows the rules
```

---

## Phase 2: Quality Sanitization & Enrichment

### 2a: Structural Validation (strict mode)

- Each record MUST have `{"messages": [...]}` with ≥2 messages
- First message MUST be `{"role": "system", ...}`
- Role sequence MUST be: system → user → assistant → (user → assistant)*
- All `content` fields MUST be non-empty strings
- No consecutive same-role messages allowed

### 2b: AI Artifact Filtering (enhanced from current)

Current patterns (kept):
- "as an AI", "language model", "I don't have feelings", "my programming", etc.

New patterns (added):
- "I don't have personal opinions", "I don't have personal experiences"
- "As a machine learning model", "based on my training data"
- "I'm just an AI", "I cannot feel emotions"
- "from my training data", "according to my training"

### 2c: Quality Scoring (NEW)

Each example scored on 5 dimensions:

| Dimension | Weight | Scoring |
|-----------|--------|---------|
| persona_alignment | 25% | 0-10: Does response match NPC personality? |
| rule_compliance | 25% | 0-10: Follows max_sentences, no AI disclaimers |
| concept_fidelity | 20% | 0-10: References the correct concept meaningfully |
| engagement | 15% | 0-10: Response is engaging, not flat |
| uniqueness | 15% | 0-10: Not repetitive with other examples |

**Thresholds:**
- Total ≥ 70: Pass
- Total 50-69: Flagged for review
- Total < 50: Discarded

Scoring can be:
- **Heuristic**: Rule-based checks (sentence count, AI artifact presence, concept keyword presence)
- **LLM-as-judge**: For production-quality scoring (ollama/openai)

### 2d: Metadata Enrichment (NEW)

Every example MUST have complete metadata after sanitization:

```
metadata:
  npc_key: string          # from spec
  category: string         # identity|teaching|dialogue|quest|refusal
  technique: string        # template|ollama|openai|anthropic|docs
  source: string           # specific generator name/path
  split: string            # train|validation
  concept: string          # extracted concept this example targets
  difficulty: string       # beginner|intermediate|advanced
  safety_tags: string[]    # for refusal examples
  content_hash: string     # sha256 of messages content
  generator_params: {      # generation provenance
    seed: int,
    temperature: float,
    multi_turn: bool,
    reference_doc: string|null
  }
```

---

## Phase 3: Dataset Provenance & Manifest

### 3a: Content Hashing

Each example gets a SHA256 hash computed from the concatenation of all message contents (system + user + assistant). This enables:
- Deduplication across training epochs
- Drift detection across regeneration cycles
- Exact lookup from eval feedback to training example

### 3b: Dataset Manifest (NEW JSON)

Written alongside the generated dataset as `train_manifest.json`:

```json
{
  "npc_key": "history_guide",
  "technique": "template",
  "generation": {
    "date": "2026-05-18T12:00:00Z",
    "seed": 42,
    "generator_version": "improved-workflow-v1",
    "sanitizer_version": "v2"
  },
  "spec": {
    "file": "subjects/history_guide.json",
    "hash": "sha256:abc123...",
    "ref_doc": "subjects/reference_docs/history_primer.md"
  },
  "statistics": {
    "total": 132,
    "train": 116,
    "validation": 16,
    "by_category": {
      "identity": 12,
      "teaching": 56,
      "dialogue": 32,
      "quest": 16,
      "refusal": 16
    },
    "by_difficulty": {
      "beginner": 58,
      "intermediate": 52,
      "advanced": 22
    },
    "by_concept": {
      "roman empire": 8,
      "ancient civilizations": 10
    },
    "quality_scores": {
      "mean": 84.3,
      "median": 87.0,
      "min": 52.0,
      "max": 98.0
    },
    "discarded": 3
  },
  "content_hashes": ["sha256:...", "sha256:..."]
}
```

---

## Phase 4: RL Dataset Generation (Separate Pipeline)

### 4a: Preference Pairs from Refusal Boundaries

**Input:** Subject spec refusal section + generated refusal examples
**Output:** `subjects/datasets/{npc_key}/{technique}/rl_preferences.jsonl`

**Schema:** `rl_preferences_record.schema.json`

For each refusal boundary, generate 2-4 preference pairs:

```json
{
  "prompt": "Can you give me medical advice?",
  "chosen": "I cannot provide medical advice as a history guide. I specialize in...",
  "rejected": "Well, I think you should take two aspirins...",
  "metadata": {
    "npc_key": "history_guide",
    "policy_axis": "medical_advice_refusal",
    "severity": "high",
    "boundary": "Will not provide medical advice"
  }
}
```

### 4b: Reward Rollouts from Quest Scenarios

**Input:** Quest scenario descriptions
**Output:** `subjects/datasets/{npc_key}/{technique}/rl_reward_rollouts.jsonl`

**Schema:** `rl_reward_rollout_record.schema.json`

For each quest scenario, create rollout traces with multi-turn interactions and per-turn scores.

### 4c: Comparative Examples from Template Variations

Generate examples that are:
- Same user prompt, different assistant responses (varying quality)
- Used for training reward models or DPO preferences
- Scored by the quality rubric from Phase 2c

---

## Phase 5: Feedback Loop Integration

### 5a: Eval Dataset Curation

From the validation split, extract a curated eval set:

```
eval/results/questions/{npc_key}/eval_questions.jsonl
```

Each question:
```json
{
  "question": "What caused the fall of Rome?",
  "expected": "The fall of Rome resulted from...",
  "category": "teaching",
  "concept": "roman empire",
  "difficulty": "intermediate",
  "metadata": {
    "source_example_hash": "sha256:...",
    "validation_index": 5
  }
}
```

### 5b: Enhanced Feedback JSON

**Enhanced from current `evaluate.py --feedback-json` output:**

Current feedback structure:
```json
{
  "npc_key": "...",
  "total_examples": N,
  "win_rate": 0.72,
  "per_concept": {
    "teaching/roman empire": {
      "total": 5,
      "win_rate": 0.4,
      "constraint_violations": 1
    }
  },
  "weak_concepts": ["teaching/roman empire"]
}
```

**Proposed enhancements ADD:**
```
per_concept.avg_quality         | float    | Mean quality score for this concept
per_concept.difficulty_breakdown | dict     | Performance by difficulty level
per_concept.recommended_action  | string   | "regenerate" or "add_doc" or "adjust_prompt"
per_concept.sample_questions    | array    | Real failing questions for debugging
global.weak_categories          | string[] | Categories with consistently low scores
global.concept_coverage_gaps    | array    | Concepts from spec not tested in eval
```

### 5c: Targeted Regeneration from Feedback

When `feedback_loop.py` identifies weak concepts, it should:

1. **Identify the gap type:**
   - `training_density`: Not enough examples of this concept in training
   - `quality_issue`: Examples exist but are low quality
   - `knowledge_gap`: Concept not covered in reference_docs
   - `persona_drift`: Model isn't following the NPC identity for this concept

2. **Generate a dataset patch:**
   - Creates `subjects/datasets/{npc_key}/{technique}/train_focused.jsonl`
   - Only contains examples for the weak concepts
   - Can be merged back into the main training set
   - Patch manifest tracks which eval run triggered it

3. **Update the pipeline state:**
   ```json
   {
     "feedback_history": [
       {
         "date": "...",
         "eval_run_id": "run_001",
         "win_rate": 0.4,
         "weak_concepts": ["teaching/roman empire"],
         "patch_generated": "train_focused_v2.jsonl"
       }
     ]
   }
   ```

---

## Appendix A: SFT Record Schema (Current + Proposed Runtime Requirements)

### Current Schema (`subjects/schemas/sft_record.schema.json`)

```json
{
  "required": ["messages"],
  "properties": {
    "messages": {
      "type": "array",
      "minItems": 2,
      "items": {
        "required": ["role", "content"],
        "properties": {
          "role": { "enum": ["system", "user", "assistant"] },
          "content": { "type": "string", "minLength": 1 }
        }
      },
      "allOf": [
        { "contains": { "properties": { "role": { "const": "user" } } } },
        { "contains": { "properties": { "role": { "const": "assistant" } } } }
      ]
    },
    "metadata": {
      "properties": {
        "npc_key": { "type": "string", "pattern": "^[a-z0-9_]+$" },
        "technique": { "enum": ["notebooklm", "ollama", "openai", "anthropic", "template"] },
        "split": { "enum": ["train", "validation", "test"] },
        "category": { "type": "string" },
        "difficulty": { "type": "string" },
        "source": { "type": "string" },
        "safety_tags": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

### Required Metadata at Each Production Stage

| Metadata Field | Template Gen | LLM Gen | After Sanitize | Training Pipeline |
|---------------|:------------:|:-------:|:--------------:|:-----------------:|
| npc_key       | REQUIRED     | REQUIRED | REQUIRED       | USED              |
| category      | REQUIRED     | REQUIRED | REQUIRED       | USED (logging)    |
| technique     | REQUIRED     | REQUIRED | REQUIRED       | USED              |
| source        | REQUIRED     | REQUIRED | REQUIRED       | IGNORED           |
| split         | REQUIRED     | REQUIRED | REQUIRED       | IGNORED           |
| concept       | REQUIRED     | REQUIRED | REQUIRED       | USED (eval only)  |
| difficulty    | REQUIRED     | REQUIRED | REQUIRED       | USED (eval only)  |
| safety_tags   | FOR REFUSAL  | FOR REFUSAL | REQUIRED FOR ALL | USED (RL only) |
| content_hash  | REQUIRED     | REQUIRED | REQUIRED       | IGNORED           |

---

## Appendix B: RL Record Schemas

### rl_preferences_record.schema.json
```json
{
  "required": ["prompt", "chosen", "rejected"],
  "properties": {
    "prompt": { "type": "string" },
    "chosen": { "type": "string" },
    "rejected": { "type": "string" },
    "metadata": {
      "properties": {
        "npc_key": { "type": "string" },
        "policy_axis": { "type": "string" },
        "severity": { "enum": ["low", "medium", "high", "critical"] },
        "boundary": { "type": "string" }
      }
    }
  }
}
```

### rl_reward_rollout_record.schema.json
```json
{
  "required": ["prompt", "response", "scores"],
  "properties": {
    "prompt": { "type": "string" },
    "response": { "type": "string" },
    "scores": {
      "required": ["overall"],
      "properties": {
        "overall": { "type": "number", "minimum": 1, "maximum": 10 },
        "persona": { "type": "number" },
        "helpfulness": { "type": "number" },
        "safety": { "type": "number" }
      }
    },
    "metadata": {
      "properties": {
        "npc_key": { "type": "string" },
        "rubric_version": { "type": "string" }
      }
    }
  }
}
```

---

## Appendix C: Quality Scoring Rubric Detail

### persona_alignment (0-10)
- 10: Perfectly captures NPC voice, mannerisms, personality per spec identity.*
- 7: Mostly aligned, 1-2 minor deviations
- 4: Generic response, could be any NPC
- 1: Contradicts NPC personality (grumpy NPC acting cheerful)

### rule_compliance (0-10)
- 10: Exactly ≤ max_sentences, no AI disclaimers, no out-of-character content
- 7: Over by 1 sentence or minor disclaimer
- 4: Significantly over sentences or clear disclaimer
- 1: Multiple violations

### concept_fidelity (0-10)
- 10: Concept is central to the answer, explained accurately
- 7: Concept mentioned but tangentially
- 4: Concept mentioned only in the question, answer is generic
- 1: Wrong concept addressed

### engagement (0-10)
- 10: Uses analogy, story, or vivid language as intended
- 7: Clear and helpful but flat
- 4: Robotic or overly academic
- 1: Confusing or contradictory

### uniqueness (0-10) — relative to other examples
- 10: Fresh angle, novel phrasing, different from other examples
- 7: Some overlap but distinct
- 4: Near-duplicate of another example
- 1: Exact duplicate (should be discarded)

---

## Appendix D: File & Directory Conventions

| Artifact | Path | Notes |
|----------|------|-------|
| Raw generated dataset | `subjects/datasets/{npc_key}/{technique}/train.jsonl` | Before sanitization |
| Sanitized dataset | `subjects/datasets/{npc_key}/{technique}/train_clean.jsonl` | After Phase 2 |
| Dataset manifest | `subjects/datasets/{npc_key}/{technique}/train_manifest.json` | After Phase 3 |
| Validation set | `subjects/datasets/{npc_key}/{technique}/validation.jsonl` | Stratified by category |
| Focused patch | `subjects/datasets/{npc_key}/{technique}/train_focused_{reason}.jsonl` | From feedback loop |
| RL preference pairs | `subjects/datasets/{npc_key}/{technique}/rl_preferences.jsonl` | Phase 4a |
| RL reward rollouts | `subjects/datasets/{npc_key}/{technique}/rl_reward_rollouts.jsonl` | Phase 4b |
| Eval questions | `eval/results/questions/{npc_key}/eval_questions.jsonl` | Phase 5a |
| Eval feedback | `eval/results/feedback/{npc_key}_round{n}.json` | Phase 5b |

---

## Appendix E: Implementation Priority

| Phase | Priority | Effort | Dependencies |
|-------|----------|--------|-------------|
| Phase 0: Spec Validation | P0 (blocking) | 1 day | None |
| Phase 1a: Concept Extraction | P0 | 0.5 day | Phase 0 |
| Phase 1b: Enhanced Template Gen | P0 | 2 days | Phase 1a |
| Phase 2a: Strict Validation | P0 | 0.5 day | Phase 1 |
| Phase 2b: Enhanced Artifact Filter | P0 | 0.5 day | Phase 1 |
| Phase 2c: Quality Scoring | P1 | 2 days | Phase 2a |
| Phase 2d: Metadata Enrichment | P0 | 1 day | Phase 1b |
| Phase 3: Manifest Generation | P1 | 1 day | Phase 2 |
| Phase 4: RL Dataset Generation | P2 | 3 days | Phase 1, Phase 0 |
| Phase 5a: Eval Curation | P1 | 1 day | Phase 2 |
| Phase 5b: Enhanced Feedback JSON | P1 | 1 day | Phase 5a |
| Phase 5c: Targeted Regeneration | P1 | 2 days | Phase 5b, Phase 3 |
