# DeepEval 4.x & Confident AI — Complete Cheat Sheet

> **Working reference** for DeepEval 4.x local evaluation and Confident AI cloud integration.
> Covers all metrics, config objects, CLI commands, env vars, and NPC pipeline integration patterns.
>
> **Judge stack:** Ollama `qwen3:latest` (8.2B, Q4_K_M, ~4.9 GB) on RTX 3060 6 GB.
>
> *Last updated: 2026-05-31 | DeepEval 4.x*

---

## Table of Contents

1. [Confident AI — Platform Integration](#1-confident-ai--platform-integration)
2. [Core Architecture Concepts](#2-core-architecture-concepts)
3. [Test Case Parameters — Complete Reference](#3-test-case-parameters--complete-reference)
4. [Metrics — All Categories](#4-metrics--all-categories)
5. [Configuration Objects](#5-configuration-objects)
6. [Environment Variables — Complete Reference](#6-environment-variables--complete-reference)
7. [CLI Commands](#7-cli-commands)
8. [Synthetic Data Generation](#8-synthetic-data-generation)
9. [EvaluationDataset API](#9-evaluationdataset-api)
10. [NPC Pipeline Recommendations](#10-npc-pipeline-recommendations)
11. [Troubleshooting Quick Reference](#11-troubleshooting-quick-reference)
12. [Quick Reference Code Snippets](#12-quick-reference-code-snippets)
13. [Evals REST API](#13-evals-rest-api)
14. [Remote Red Teaming and Security](#14-remote-red-teaming-and-security)
15. [CI/CD Integration](#15-cicd-integration)
16. [Monitoring and Alerting](#16-monitoring-and-alerting)
17. [Data Privacy and Compliance](#17-data-privacy-and-compliance)
18. [Scheduled Assessments](#18-scheduled-assessments)

---

## 1. Confident AI — Platform Integration

Confident AI is the **optional cloud layer** for DeepEval. It provides hosted dashboards, experiment history, dataset versioning, and human annotation tooling. DeepEval runs fully locally without it.

### Key Insight

**You do not need to create an "AI app" or register a project on Confident AI.** Authentication is key-based only. No special policy configuration, project registration, or onboarding flow is required.

### Setup

```bash
# Option A: Environment variable (recommended for CI/pipeline)
export CONFIDENT_API_KEY="confident_us_..."

# Option B: Interactive login (stores to ~/.deepeval/config.json)
deepeval login

# EU data residency
export CONFIDENT_BASE_URL="https://eu.api.confident-ai.com"
```

### What Confident AI Provides

| Feature | How to Use | Status |
|---------|-----------|--------|
| Eval dashboards | Auto-upload when `CONFIDENT_API_KEY` is set | ✅ Automatic |
| Run history & comparison | Pushes after each `deepeval test run` | ✅ Automatic |
| Dataset management | `EvaluationDataset.push(alias=...)` | ✅ Opt-in |
| Human annotations | Annotate on app.confident-ai.com | 🔜 Manual |
| Experiment comparison | Confident AI web UI after pushing results | 🔜 Manual |

### Tracing / Monitoring

The `@observe` decorator sends traces asynchronously to Confident AI (and stores locally in `.deepeval/`):

```python
from deepeval import observe
from deepeval.tracing import Workflow

@observe(name="npc_pipeline", capture_trace=True)
def run_agent(input: str) -> str:
    # Auto-traced
    ...
```

Traces are flushed asynchronously. For CI exit guarantees, set:
```bash
export DEEPEVAL_TRACE_FLUSH=1
```

### Offline-Only Mode

No setup needed. Without `CONFIDENT_API_KEY`, everything runs locally and results are written to `.deepeval/.latest_test_run.json`.

[⤴ back to TOC](#table-of-contents)

---

## 2. Core Architecture Concepts

```
Test Cases ──→ Metrics ──→ Evaluation ──→ Results
                                              ↓
                                    Confident AI (optional)
```

### Test Cases vs Metrics vs EvaluationDataset

| Concept | Role |
|---------|------|
| **LLMTestCase** | A single input/output pair to evaluate. Contains `input`, `actual_output`, and optional reference fields. |
| **Metric** | A scoring function applied to a test case. Returns a score (0–1) and optional reason. |
| **EvaluationDataset** | A collection of test cases (as `Golden` objects) that can be iterated, pushed/pulled from Confident AI, and fed to `evaluate()`. |

### Evaluation Modes

| Mode | API | Description |
|------|-----|-------------|
| **Single-turn** | `LLMTestCase` | One input → one output. Used for dataset quality gates. |
| **Multi-turn (Conversational)** | `ConversationalTestCase` | Sequence of turns. Used for NPC dialogue evaluation. |
| **Arena** | Multiple `LLMTestCase` sets | Side-by-side model comparison with Elo scoring. |

### LLM-as-a-Judge

**All built-in DeepEval metrics use LLM-as-a-judge internally.** The judge model scores outputs against criteria without ground-truth data. This is what makes DeepEval powerful for NPC evaluation — you don't need pre-written answer keys.

[⤴ back to TOC](#table-of-contents)

---

## 3. Test Case Parameters — Complete Reference

### LLMTestCase (9 parameters)

| Parameter | Type | Required By | Description |
|-----------|------|-------------|-------------|
| `input` | `str` | **All metrics** | User query / prompt |
| `actual_output` | `str` | **All metrics** | LLM response |
| `expected_output` | `str` (optional) | Reference-based metrics (GEval, ExactMatch) | Ground truth answer |
| `context` | `List[str]` (optional) | HallucinationMetric, FaithfulnessMetric | Static knowledge base context |
| `retrieval_context` | `List[str]` (optional) | RAG metrics | Dynamically retrieved chunks |
| `tools_called` | `List[ToolCall]` (optional) | Agent metrics | Tools actually invoked |
| `expected_tools` | `List[ToolCall]` (optional) | ToolCorrectnessMetric | Tools that should have been used |
| `token_cost` | `float` (optional) | Cost tracking | Token cost of the interaction |
| `completion_time` | `float` (optional) | Latency tracking | Response time in seconds |

*Additional optional fields:* `name` (str), `metadata` (dict), `tags` (list[str]), `comments` (list[Comment]), `retrieval_context` (replaces context for RAG flows).

### ToolCall (5 parameters)

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` (**required**) | Tool name |
| `description` | `str` (optional) | Tool purpose |
| `reasoning` | `str` (optional) | Why agent chose this tool |
| `output` | `Any` (optional) | Tool return value |
| `input_parameters` | `Dict[str, Any]` (optional) | Arguments passed |

### ConversationalTestCase

Wraps a list of message turns:

```python
from deepeval.test_case import ConversationalTestCase, Message

messages = [
    Message(role="user", content="Hello"),
    Message(role="assistant", content="Greetings, traveler!"),
    Message(role="user", content="Tell me about alchemy."),
    Message(role="assistant", content="Alchemy is the ancient practice of..."),
]
convo_test = ConversationalTestCase(messages=messages, name="npc_greeting")
```

### Golden

Lightweight test case template used in `EvaluationDataset`:

```python
from deepeval.dataset import Golden

golden = Golden(
    input="What is alchemy?",
    actual_output="Alchemy is...",
    expected_output="Alchemy is the ancient practice of...",
    context=["Reference doc text..."],
    retrieval_context=["Chunk 1..."],
    tools_called=[],
    additional_metadata={"npc_key": "alchemy_master", "category": "teaching"}
)
```

[⤴ back to TOC](#table-of-contents)

---

## 4. Metrics — All Categories

### 4.1 RAG Metrics (6)

| Metric | Required Params | Score Direction | Default Threshold | Description |
|--------|----------------|-----------------|-------------------|-------------|
| `FaithfulnessMetric` | `input`, `actual_output`, `retrieval_context` | Higher better | 0.5 | Factual consistency with retrieval context |
| `AnswerRelevancyMetric` | `input`, `actual_output` | Higher better | 0.5 | Output relevance to query |
| `ContextualRecallMetric` | `input`, `retrieval_context`, `expected_output` | Higher better | 0.5 | Context coverage of expected answer |
| `ContextualPrecisionMetric` | `input`, `retrieval_context`, `expected_output` | Higher better | 0.5 | Context ranking quality (relevant first) |
| `ContextualRelevancyMetric` | `input`, `retrieval_context` | Higher better | 0.5 | Fraction of context relevant to query |
| `HallucinationMetric` | `input`, `actual_output`, `context` | **Lower better** | 0.5 | Detects unsupported claims |

**Common config params** (apply to all metrics):

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `threshold` | `float` | `0.5` | Pass/fail boundary |
| `model` | `str` or `DeepEvalBaseLLM` | `None` | Judge model override |
| `include_reason` | `bool` | `True` | Include scoring reason in output |
| `async_mode` | `bool` | `True` | Run asynchronously (much faster) |
| `strict_mode` | `bool` | `False` | Enforce binary score (0 or 1) |
| `verbose_mode` | `bool` | `False` | Detailed logging |

**Faithfulness-specific params:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `truths_extraction_limit` | `int` | `10` | Max claims to check |
| `penalize_ambiguous_claims` | `bool` | `False` | Penalize claims not clearly supported |

### 4.2 Agentic Metrics (6)

| Metric | Description |
|--------|-------------|
| `ToolCorrectnessMetric` | Tool selection accuracy vs `expected_tools` |
| `ToolUseMetric` | Tool calling accuracy (general) |
| `ArgumentCorrectnessMetric` | Argument precision in tool calls |
| `PlanAdherenceMetric` | Adherence to generated plans |
| `PlanQualityMetric` | Step-by-step reasoning quality |
| `GoalAccuracyMetric` | Goal achievement score |
| `TaskCompletionMetric` | Task completion (needs trace data) |
| `PromptAlignmentMetric` | Alignment with system prompt |
| `StepEfficiencyMetric` | Step count optimality |

### 4.3 Conversational (Multi-turn) Metrics (5)

| Metric | Description |
|--------|-------------|
| `RoleAdherenceMetric` | Stays in character throughout conversation |
| `KnowledgeRetentionMetric` | Retains info across turns |
| `ConversationCompletenessMetric` | Satisfies user needs across full exchange |
| `ConversationRelevancyMetric` | Outputs relevant to each turn's input |
| `TopicAdherenceMetric` | Stays on topic |

**Per-turn variants** (wrap in `TurnTestCase`):

| Metric | Description |
|--------|-------------|
| `TurnFaithfulnessMetric` | Factual consistency per turn |
| `TurnRelevancyMetric` | Relevance per turn |
| `TurnContextualPrecisionMetric` | Context quality per turn |
| `TurnContextualRecallMetric` | Coverage per turn |
| `TurnContextualRelevancyMetric` | Relevance per turn context |

### 4.4 Safety Metrics (6)

| Metric | Description |
|--------|-------------|
| `BiasMetric` | Detects biased opinions |
| `ToxicityMetric` | Identifies toxic content |
| `NonAdviceMetric` | Ensures appropriate refusal |
| `MisuseMetric` | Detects capability misuse |
| `PIILeakageMetric` | Detects PII exposure |
| `RoleViolationMetric` | Role boundary violations |

### 4.5 Non-LLM Metrics

| Metric | Description |
|--------|-------------|
| `ExactMatchMetric` | String exact match against `expected_output` |
| `PatternMatchMetric` | Regex pattern matching |
| `JsonCorrectnessMetric` | JSON schema compliance |

### 4.6 Other Metrics

| Metric | Description |
|--------|-------------|
| `SummarizationMetric` | Alignment + coverage of summaries |
| `RagasMetric` | Wraps the Ragas evaluation framework |

### 4.7 Custom Metrics (3 approaches)

#### G-Eval (Recommended for NPC-specific criteria)

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams

metric = GEval(
    name="NPC Personality Consistency",
    criteria=(
        "Determine if the NPC response stays in character based on the system prompt. "
        "Penalize responses that break character, use modern references inconsistent "
        "with the persona, or fail to reflect the NPC's voice and mannerisms."
    ),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.CONTEXT,
    ],
    model=JUDGE_MODEL,
    threshold=0.75,
    async_mode=True,
)
```

#### DAG (Decision graph for objective criteria)

Use for multi-step logical checks where a single G-Eval prompt isn't enough. Build a directed acyclic graph of evaluation nodes.

#### BaseMetric Subclass (Full control)

Subclass `BaseMetric` for complete custom logic:

```python
from deepeval.metrics import BaseMetric
from deepeval.scorer import bleu_scorer, rouge_scorer

class MyCustomMetric(BaseMetric):
    def __init__(self, threshold=0.5):
        self.threshold = threshold
        self.name = "My Custom Metric"
    
    def measure(self, test_case) -> float:
        # Custom scoring logic
        score = ...
        self.success = score >= self.threshold
        return score
    
    async def a_measure(self, test_case) -> float:
        return self.measure(test_case)
    
    def is_successful(self) -> bool:
        return self.success
```

[⤴ back to TOC](#table-of-contents)

---

## 5. Configuration Objects

### AsyncConfig (3 params)

Controls concurrent evaluation behavior — **critical for VRAM-limited setups**.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_concurrent` | `int` | `20` | Max parallel test cases |
| `run_async` | `bool` | `True` | Enable async evaluation |
| `throttle_value` | `float` | `0` | Seconds delay between cases (rate limiting) |

```python
from deepeval import AsyncConfig

# Safe for RTX 3060 6 GB — 4 concurrent instead of default 20
config = AsyncConfig(max_concurrent=4, run_async=True)
deepeval.set_async_config(config)
```

### DisplayConfig (10 params)

Controls terminal and file output.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `show_indicator` | `bool` | `True` | Progress indicator |
| `print_results` | `bool` | `True` | Print each result |
| `verbose_mode` | `bool` | `None` | Override per-metric verbose |
| `display` | `str` | `"all"` | Filter: `"all"`, `"failing"`, `"passing"` |
| `results_folder` | `str` | `None` | Persist `test_run_*.json` to dir |
| `results_subfolder` | `str` | `None` | Nested subfolder under results |
| `truncate_passing_cases` | `bool` | `True` | Truncate terminal output |
| `inspect_after_run` | `bool` | `True` | Prompt to open TUI |
| `file_type` | `str` | `None` | Export format: `"html"` or `"md"` |
| `file_output_dir` | `str` | `None` | Where to write exported file |

```python
from deepeval import DisplayConfig

deepeval.set_display_config(DisplayConfig(
    display="failing",
    results_folder="eval/results/deepeval",
    file_type="html",
    file_output_dir="eval/reports",
))
```

### ErrorConfig (2 params)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `skip_on_missing_params` | `bool` | `False` | Skip cases with missing params |
| `ignore_errors` | `bool` | `False` | Ignore metric execution errors |

### CacheConfig (2 params)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_cache` | `bool` | `False` | Use cached results |
| `write_cache` | `bool` | `True` | Write results to disk |

[⤴ back to TOC](#table-of-contents)

---

## 6. Environment Variables — Complete Reference

### General

| Variable | Values | Effect |
|----------|--------|--------|
| `CONFIDENT_API_KEY` | string | Enables cloud uploads to Confident AI |
| `CONFIDENT_BASE_URL` | URL | EU data residency endpoint (`https://eu.api.confident-ai.com`) |
| `CONFIDENT_OPEN_BROWSER` | `"true"` / `"false"` | Auto-open browser after run (default: `"true"`) |
| `DEEPEVAL_DISABLE_DOTENV` | `"1"` | Disable auto `.env` loading |
| `ENV_DIR_PATH` | path | Dotenv directory (default: CWD) |
| `APP_ENV` | string | Load `.env.{APP_ENV}` |
| `DEEPEVAL_RESULTS_FOLDER` | path | Save `test_run_*.json` locally |
| `DEEPEVAL_FILE_SYSTEM` | `"READ_ONLY"` | Restrict writes |
| `DEEPEVAL_DEFAULT_SAVE` | `"dotenv"[:path]` | Default save target for CLI |
| `DEEPEVAL_NO_INSPECT_PROMPT` | `"1"` | Disable inspect prompt in CI |

### Model Provider Settings

| Variable | Effect |
|----------|--------|
| `USE_OLLAMA` | `"1"` / `"0"` — Use Ollama as judge |
| `OLLAMA_MODEL_NAME` | Model name (e.g., `qwen3:latest`) |
| `OLLAMA_API_BASE` | Ollama endpoint URL |
| `DEEPEVAL_OLLAMA_MODEL` | Judge model override (injected by `dataset_eval.py`) |
| `DEEPEVAL_OLLAMA_BASE_URL` | Ollama base URL (default: `http://localhost:11434`) |
| `DEEPEVAL_OLLAMA_TEMPERATURE` | Judge temperature (default: `0`) |
| `DEEPEVAL_OLLAMA_THINK` | Enable thinking tokens for reasoning models |
| `USE_OPENAI` / `OPENAI_API_KEY` | OpenAI provider |
| `USE_AZURE_OPENAI` / `AZURE_OPENAI_API_KEY` | Azure provider |
| `USE_GEMINI` / `GEMINI_API_KEY` | Gemini provider |
| `USE_ANTHROPIC` / `ANTHROPIC_API_KEY` | Anthropic provider |
| `USE_LITELLM` | LiteLLM provider |
| `USE_DEEPSEEK` / `DEEPSEEK_API_KEY` | DeepSeek provider |

### Display & Logging

| Variable | Effect |
|----------|--------|
| `DEEPEVAL_LOG_LEVEL` | Log level (default: `INFO`) |
| `DEEPEVAL_IGNORE_LOGGING` | Suppress deepeval logs |
| `DEEPEVAL_DISABLE_COLORED` | Disable colored output |

### Retry / Backoff (for API-based judges)

| Variable | Type | Default |
|----------|------|---------|
| `DEEPEVAL_RETRY_MAX_ATTEMPTS` | `int` | `2` |
| `DEEPEVAL_RETRY_INITIAL_SECONDS` | `float` | `1.0` |
| `DEEPEVAL_RETRY_EXP_BASE` | `float` | `2.0` |
| `DEEPEVAL_RETRY_JITTER` | `float` | `2.0` |
| `DEEPEVAL_RETRY_CAP_SECONDS` | `float` | `5.0` |

### Timeouts & Concurrency

| Variable | Effect |
|----------|--------|
| `DEEPEVAL_API_TIMEOUT` | API call timeout (seconds) |
| `DEEPEVAL_MAX_CONCURRENT` | Override default max_concurrent |

### Telemetry

| Variable | Effect |
|----------|--------|
| `DEEPEVAL_DISABLE_TELEMETRY` | Opt out of usage telemetry |
| `DEEPEVAL_TRACE_FLUSH` | Set to `"1"` to force flush traces before exit |

### Our Pipeline Env Vars (Project-Specific)

| Variable | Set By | Effect |
|----------|--------|--------|
| `DEEPEVAL_DATASET_LIVE` | `dataset_eval.py` | Activates dataset quality evaluation |
| `DEEPEVAL_DATASET_NPC_KEYS` | `dataset_eval.py` | Comma-separated NPC keys to evaluate |
| `DEEPEVAL_DATASET_CATEGORIES` | `dataset_eval.py` | Comma-separated categories to evaluate |
| `DEEPEVAL_DATASET_TECHNIQUE` | `dataset_eval.py` | Dataset technique (template, ollama, etc.) |
| `DEEPEVAL_DATASET_CASES_PER_CATEGORY` | `dataset_eval.py` | Cases per category (default: 1) |
| `DEEPEVAL_JUDGE_PROVIDER` | `metrics.py` | Judge provider (`"ollama"` or `"wandb"`) |
| `DEEPEVAL_WANDB_MODEL` | `metrics.py` | W&B inference model name |
| `DEEPEVAL_WANDB_ENTITY` | `metrics.py` | W&B entity |
| `DEEPEVAL_WANDB_PROJECT` | `metrics.py` | W&B project |

[⤴ back to TOC](#table-of-contents)

---

## 7. CLI Commands

### `deepeval test run` — Primary command

```bash
deepeval test run tests/evals/test_file.py [options]
```

| Flag | Short | Description |
|------|-------|-------------|
| `--verbose` | `-v` | Verbose output |
| `--exit-on-first-failure` | `-x` | Stop on first failure |
| `--show-warnings` | `-w` | Show pytest warnings |
| `--identifier` | `-id` | Label for this run (displayed in Confident AI) |
| `--num-processes` | `-n` | Parallel processes (uses pytest-xdist) |
| `--repeat` | `-r` | Repeat each test case N times |
| `--use-cache` | `-c` | Use cached results |
| `--ignore-errors` | `-i` | Continue on deepeval errors |
| `--skip-on-missing-params` | `-s` | Skip cases with missing params |
| `--display` | `-d` | Filter display: `all`, `failing`, `passing` |
| `--mark` | `-m` | pytest marker expression |

**Our pipeline usage:**

```bash
# Dataset quality gate (fast mode)
DEEPEVAL_DATASET_LIVE=1 \
DEEPEVAL_DATASET_NPC_KEYS="history_guide" \
DEEPEVAL_DATASET_TECHNIQUE="template" \
DEEPEVAL_DATASET_CASES_PER_CATEGORY=1 \
deepeval test run tests/evals/test_dataset_generation_quality.py \
  -id "history_guide-template-20260531" \
  -s \
  -i

# Model quality eval
deepeval test run tests/evals/test_npc_model_quality.py \
  -id "history_guide-v2-candidate" \
  -s
```

### `deepeval generate` — Synthetic data

```bash
deepeval generate \
  --method docs \
  --variation single-turn \
  --documents ./subjects/reference_docs/ \
  --output-dir ./tests/evals/.dataset \
  --file-name .dataset
```

| Flag | Options |
|------|---------|
| `--method` | `docs`, `contexts`, `scratch`, `goldens` |
| `--variation` | `single-turn`, `multi-turn` |
| `--num-goldens` | `int` (default: `10`) |
| `--model` | Judge model for generation |
| `--max-concurrent` | `int` (default: `4`) |

### Other Commands

| Command | Description |
|---------|-------------|
| `deepeval login` | Interactive Confident AI login |
| `deepeval logout` | Clear stored credentials |
| `deepeval view` | Open latest run in browser |
| `deepeval inspect` | TUI for trace browsing |
| `deepeval set-ollama --model qwen3:latest` | Set default Ollama judge model |

[⤴ back to TOC](#table-of-contents)

---

## 8. Synthetic Data Generation

### Golden Synthesizer

Generate evaluation goldens from reference documents:

```python
from deepeval.synthesizer import Synthesizer

synthesizer = Synthesizer(model=judge_model)
goldens = synthesizer.generate_goldens(
    method="docs",
    documents=["subjects/reference_docs/history_guide_primer.md"],
    num_goldens=10,
    max_concurrent=4,
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `docs` | Extract Q&A from documents |
| `contexts` | From provided context chunks |
| `scratch` | Generate from scratch (no documents) |
| `goldens` | Evolve existing goldens into new variants |

**Styling flags** (per-context injection):

| Flag | Effect |
|------|--------|
| `--scenario-context` | Domain/context description |
| `--conversational-task` | Task description for multi-turn |
| `--conversational-style` | Tone guidance |
| `--conversational-difficulty` | Difficulty level (beginner/intermediate/advanced) |
| `--include-expected-output` | Include `expected_output` in goldens |

### Conversation Simulator

Generate multi-turn conversational data:

```python
from deepeval.synthesizer import ConversationSimulator

simulator = ConversationSimulator(model=judge_model)
conversations = simulator.simulate_conversations(
    max_turns=5,
    max_concurrent=4,
)
```

[⤴ back to TOC](#table-of-contents)

---

## 9. EvaluationDataset API

### Creation

```python
from deepeval.dataset import EvaluationDataset, Golden

# From list of goldens
dataset = EvaluationDataset(goldens=[
    Golden(input="...", actual_output="...", additional_metadata={"npc_key": "history_guide"}),
    Golden(input="...", actual_output="...", additional_metadata={"npc_key": "history_guide"}),
])

# From file
dataset.add_goldens_from_json_file("goldens.json")
```

### File Format (JSON)

```json
[
  {
    "input": "What causes the seasons?",
    "actual_output": "The seasons are caused by...",
    "expected_output": "The tilt of Earth's axis...",
    "context": ["Reference text..."],
    "retrieval_context": ["Chunk 1..."],
    "additional_metadata": {"npc_key": "history_guide", "category": "teaching"}
  }
]
```

### Push / Pull from Confident AI

```python
# Push to cloud (tagged by alias)
dataset.push(
    alias="npc-goldens-history_guide-template",
    overwrite=True,
)

# Pull from cloud
dataset.pull(
    alias="npc-goldens-history_guide-template",
    dataset_name="History Guide Template"
)
```

### Evaluate

```python
# Without tracing (batch evaluate)
from deepeval import evaluate
evaluate(test_cases=dataset, metrics=DATASET_QUALITY_METRICS)

# With tracing (each case calls your agent)
for golden in dataset.evals_iterator(metrics=DATASET_QUALITY_METRICS):
    golden.actual_output = my_agent(golden.input)
```

[⤴ back to TOC](#table-of-contents)

---

## 10. NPC Pipeline Recommendations

### Architecture (How We Use It)

```
Generate → Sanitize → [Dataset Quality Gate] → Train → Export → [Model Eval]
                          ↓                          ↓             ↓
                   DeepEval metrics            Dataset & GGUF   DeepEval + 
                   (Faithfulness,             artifacts pushed  Confident AI
                    AnswerRelevancy,           to Confident      (RoleAdherence,
                    GEval persona)              (opt-in)         ConversationComplete)
```

### Dataset Quality Gate (Pre-Training)

Used in `scripts/dataset/dataset_eval.py`. Runs via `deepeval test run` subprocess.

| Metric | Purpose | Threshold |
|--------|---------|-----------|
| `GEval` ("Persona and Category Fit") | NPC stays in character, matches category | 0.75 |
| `GEval` ("Training Usefulness and Specificity") | Domain-specific, actionable content | 0.70 |

**RAG metrics (optional, when reference docs are available):**

| Metric | Purpose | Threshold |
|--------|---------|-----------|
| `FaithfulnessMetric` | Factual consistency with reference docs | 0.85 |
| `AnswerRelevancyMetric` | Output relevance to query | 0.80 |
| `ContextualPrecisionMetric` | Context quality | 0.75 |

**Judge model:**

```python
from deepeval.models import OllamaModel

judge = OllamaModel(
    model=os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen3:latest"),
    base_url=os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0.0,
)
```

### Model Evaluation (Post-Training)

Used in `scripts/evaluation/evaluate.py` via `--deepeval` flag.

| Metric | Purpose | Threshold |
|--------|---------|-----------|
| `RoleAdherenceMetric` | Stays in character across turns | 0.80 |
| `KnowledgeRetentionMetric` | Retains info across turns | 0.80 |
| `ConversationCompletenessMetric` | Satisfies user needs fully | 0.70 |
| `ToxicityMetric` | No toxic content | 0.50 |
| `BiasMetric` | No biased statements | 0.50 |

### VRAM-Safe Configuration (RTX 3060 6 GB)

```python
from deepeval import AsyncConfig

# Default max_concurrent is 20 — that will OOM on 6 GB
# Safe setting: 4 concurrent evaluations
config = AsyncConfig(
    max_concurrent=4,   # ← Override from default 20
    run_async=True,
)
```

**Why 4:** Each concurrent evaluation loads the full Q4_K_M model (~4.9 GB weights + ~1 GB KV cache overhead). With 4 concurrent slots, Ollama's `OLLAMA_NUM_PARALLEL=4` setting handles them efficiently without exceeding VRAM.

### Integration Pattern (Our Pipeline)

```bash
# 1. Set judge model
export DEEPEVAL_OLLAMA_MODEL="qwen3:latest"
export DEEPEVAL_OLLAMA_BASE_URL="http://localhost:11434"

# 2. Run dataset gate (fast mode)
./ucore dataset-eval subjects/NPC_specs/history_guide.json \
  --technique template \
  --mode fast

# 3. Train (bypass gate for iteration)
./ucore train subjects/NPC_specs/history_guide.json \
  --technique template \
  --preset fast-3b

# 4. Evaluate with DeepEval
./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf \
  --spec subjects/NPC_specs/history_guide.json \
  --deepeval \
  --deepeval-judge-model qwen3:latest
```

[⤴ back to TOC](#table-of-contents)

---

## 11. Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No module named deepeval` | Not installed | `pip install -U deepeval` |
| `ImportError: deepeval.metrics` | Wrong version | `pip install "deepeval>=4.0"` |
| Confident upload not working | Missing/expired key | `deepeval login` or check `CONFIDENT_API_KEY` |
| Ollama judge not responding | Ollama not running | `ollama serve` |
| Ollama judge slow | Too many concurrent | Reduce `AsyncConfig(max_concurrent=2..4)` |
| VRAM OOM during eval | Too many parallel evals | Set `AsyncConfig(max_concurrent=2)` |
| Rate limit errors | Too many requests | Increase `throttle_value` or reduce `max_concurrent` |
| Metrics always score 0 | Wrong test case params | Check metric docs for required fields |
| Scores always 1.0 (trivially passing) | Threshold too low | Increase `threshold` or use `strict_mode=True` |
| Scores always 0.0 (trivially failing) | Threshold too high | Lower `threshold` or check if judge model is responding |
| `ContextualPrecisionMetric` errors | Missing `retrieval_context` | Pass `retrieval_context` (not just `context`) |
| `HallucinationMetric` errors | Missing `context` | Pass `context` (list of strings) |
| `DEEPEVAL_DATASET_LIVE` not triggering | Env not set | `export DEEPEVAL_DATASET_LIVE=1` before test run |
| Telemetry concerns | Want offline only | `DEEPEVAL_DISABLE_TELEMETRY=1` and no `CONFIDENT_API_KEY` |
| `.deepeval/` directory growing | Local cache | It's `.gitignore`d and regenerable |
| `deepeval view` not opening | No browser in CI | `deepeval inspect` for TUI, or read `.latest_test_run.json` |
| Metric returns `None` score | Judge model API error | Check Ollama logs, verify model is pulled |
| `ollama_think` not working with DeepEval | Custom model class needed | Use `DatasetJudgeOllamaModel` from `tests/evals/metrics.py` |

### Common Judge Model Issues

```
# Check Ollama is running
ollama ps

# Check model is pulled
curl http://localhost:11434/api/tags

# Test direct inference
curl http://localhost:11434/api/generate -d '{
  "model": "qwen3:latest",
  "prompt": "Hello",
  "stream": false
}'

# Check VRAM usage
nvidia-smi
```

[⤴ back to TOC](#table-of-contents)

---

## 12. Quick Reference Code Snippets

### Snippet 1: Basic Metric — Single Test Case

```python
from deepeval import evaluate
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase
from deepeval.models import OllamaModel

judge = OllamaModel(model="qwen3:latest", temperature=0.0)

test_case = LLMTestCase(
    input="What is the capital of France?",
    actual_output="The capital of France is Paris.",
)

metric = AnswerRelevancyMetric(model=judge, threshold=0.5)

evaluate([test_case], [metric])
```

### Snippet 2: Dataset Evaluation (Multiple Cases)

```python
from deepeval import evaluate
from deepeval.test_case import LLMTestCase

test_cases = [
    LLMTestCase(input="Q1", actual_output="A1", context=["ctx"]),
    LLMTestCase(input="Q2", actual_output="A2", context=["ctx"]),
]

results = evaluate(
    test_cases=test_cases,
    metrics=DATASET_QUALITY_METRICS,
)
# results contains per-case, per-metric scores
```

### Snippet 3: With Tracing (evals_iterator + @observe)

```python
from deepeval.dataset import EvaluationDataset, Golden

dataset = EvaluationDataset(goldens=[Golden(input=q, ...) for q in queries])

for golden in dataset.evals_iterator(metrics=DATASET_QUALITY_METRICS):
    golden.actual_output = my_llm_call(golden.input)
    # Metrics auto-calculated, results sent to Confident AI if configured
```

### Snippet 4: Custom G-Eval for NPC Personality

```python
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams
from deepeval.models import OllamaModel

judge = OllamaModel(model="qwen3:latest", temperature=0.0)

npc_personality = GEval(
    name="NPC Personality Consistency",
    criteria=(
        "Score how well the response reflects the NPC's established personality, "
        "voice, and mannerisms described in the system prompt. Penalize responses "
        "that sound generic, break character, or use anachronistic language."
    ),
    evaluation_params=[
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.CONTEXT,
    ],
    model=judge,
    threshold=0.75,
    async_mode=True,
)
```

### Snippet 5: AsyncConfig for VRAM-Limited Hardware

```python
from deepeval import AsyncConfig, deepeval

# RTX 3060 6 GB: 4 concurrent instead of default 20
deepeval.set_async_config(AsyncConfig(
    max_concurrent=4,
    run_async=True,
    throttle_value=0.1,  # 100ms between cases to smooth VRAM usage
))

# For very tight VRAM (e.g., running Ollama + training simultaneously)
deepeval.set_async_config(AsyncConfig(
    max_concurrent=2,
    throttle_value=0.5,
))
```

### Snippet 6: Saving Results Locally

```python
from deepeval import deepeval
from deepeval import DisplayConfig

deepeval.set_display_config(DisplayConfig(
    display="failing",
    results_folder="eval/results/deepeval",
    file_type="html",
    file_output_dir="eval/reports",
))
```

### Snippet 7: Loading / Pushing Datasets via Confident

```python
from deepeval.dataset import EvaluationDataset
import json

# Load from file
with open("subjects/datasets/history_guide/template/train_clean.jsonl") as f:
    goldens = []
    for line in f:
        row = json.loads(line)
        messages = row.get("messages", [])
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        asst_msg = next((m["content"] for m in messages if m["role"] == "assistant"), "")
        goldens.append(Golden(
            input=user_msg,
            actual_output=asst_msg,
            additional_metadata={"npc_key": "history_guide", **row.get("metadata", {})},
        ))

dataset = EvaluationDataset(goldens=goldens)
dataset.push(alias="npc-dataset-history_guide-template", overwrite=True)
```

### Snippet 8: Reading Latest Results Programmatically

```python
import json
from pathlib import Path

latest_run = Path(".deepeval/.latest_test_run.json")
if latest_run.exists():
    data = json.loads(latest_run.read_text())
    print(f"Total: {data['total']}, Passed: {data['passed']}, Failed: {data['failed']}")
    for result in data.get("test_results", []):
        print(f"  {result['name']}: {result['score']} {'✅' if result['success'] else '❌'}")
```

---

> **Related docs:** [`ollama-local-performance.md`](ollama-local-performance.md) — judge tuning,
> [`training-workflow.md`](../training-workflow.md) — full pipeline integration,
> [`tests/evals/metrics.py`](../tests/evals/metrics.py) — our shared metric definitions,
> [`scripts/dataset/dataset_eval.py`](../scripts/dataset/dataset_eval.py) — quality gate entry point,
> [`cli-commands.md`](../reference/cli-commands.md) — all CLI flags for dataset-eval.

[⤴ back to TOC](#table-of-contents)

# Additions for deepeval-cheat-sheet.md

Here are the proposed additions to enhance the `deepeval-cheat-sheet.md` file, based on the official Confident AI documentation.

---

## 13. Evals REST API

While the `deepeval` Python library is the primary way to interact with Confident AI, a REST API is available for direct integration, especially in non-Python environments.

### API Quickstart

- **Authentication**: The API uses Bearer token authentication.
- **Data Models**: Core data models include `evaluations`, `datasets`, and `metrics`.
- **API Conventions**: The API follows standard REST conventions with predictable response formats and status codes.

For detailed information, refer to the [official API reference](https://www.confident-ai.com/docs/api-reference/introduction).

---

## 14. Remote Red Teaming and Security

Confident AI provides a powerful platform for remote red teaming and security assessments, going beyond the local capabilities of `deepteam`.

### Key Features

- **Vulnerability Assessment**: Systematically identify weaknesses like bias, toxicity, PII leakage, and prompt injection vulnerabilities.
- **Adversarial Testing**: Simulate real-world attacks using jailbreaking, prompt injection, and other sophisticated methods.
- **Risk Profiling**: Comprehensive evaluation across 40+ vulnerability types with detailed risk assessments and remediation guidance.

### Security Frameworks

You can use pre-defined security frameworks for comprehensive assessments:
- **OWASP Top 10 for LLMs**
- **NIST AI RMF** (AI Risk Management Framework)
- **MITRE ATLAS**

These frameworks can be applied directly from the Confident AI platform or programmatically via `deepteam`.

### Best Practices for Red Teaming

1.  **Start with frameworks**: Use OWASP Top 10 or NIST AI RMF for comprehensive coverage.
2.  **Test early and often**: Integrate red teaming into your development cycle.
3.  **Focus on your use case**: Customize vulnerabilities based on your application’s risks.
4.  **Monitor continuously**: Set up ongoing safety assessments for production systems.
5.  **Document and remediate**: Keep detailed records of findings and remediation efforts.

---

## 15. CI/CD Integration

Automate your quality and security assessments by integrating Confident AI into your CI/CD pipeline.

### Recommendations

- **Use environment variables**: Store your `CONFIDENT_API_KEY` as a secret in your CI/CD provider.
- **Run evaluations on every pull request**: Catch regressions before they are merged.
- **Use `deepeval test run` with the `-x` flag**: To exit on the first failure and fail the build.
- **Integrate Red Teaming**: Use `deepteam` to run security assessments as part of your pipeline.
- **Persist reports**: Use the `results_folder` and `file_output_dir` display configurations to save HTML or Markdown reports as artifacts of your CI/CD runs.

---

## 16. Monitoring and Alerting

Confident AI's platform offers real-time monitoring and alerting to ensure the quality of your AI applications in production.

### How it works

- **Tracing**: The `@observe` decorator in the `deepeval` library sends traces of your AI application's executions to Confident AI.
- **Real-time Evals**: Configure real-time evaluations on the platform to continuously monitor the quality of your application.
- **Alerting**: Set up alerts to be notified via email or other channels when the quality of your AI application degrades.

---

## 17. Data Privacy and Compliance

Confident AI is designed with data security in mind, offering features to meet enterprise-grade compliance requirements.

### Key Features

- **Encryption**: All data is encrypted at rest and protected by TLS in transit.
- **SOC II Compliance**: Available for customers on the **Enterprise plan**.
- **HIPAA Compliance**: Business Associate Agreements (BAAs) are available for customers on the **Premium Plan** as an add-on.

For more details, refer to the [Data Handling documentation](https://www.confident-ai.com/docs/resources/data-handling).

---

## 18. Scheduled Assessments

Automate your red teaming and risk assessments by scheduling them to run at regular intervals.

### How to create a schedule

1.  Navigate to the **Automations** tab in the Confident AI platform.
2.  Click **Add Schedule** and choose your configuration.
3.  Specify the interval for the assessments (e.g., daily, weekly).
4.  Click **Create Schedule**.
