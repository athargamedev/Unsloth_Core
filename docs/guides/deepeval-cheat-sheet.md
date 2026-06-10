1|# DeepEval 4.x & Confident AI — Complete Cheat Sheet
2|
3|> **Working reference** for DeepEval 4.x local evaluation and Confident AI cloud integration.
4|> Covers all metrics, config objects, CLI commands, env vars, and NPC pipeline integration patterns.
5|>
6|> **Judge stack:** Ollama `qwen2.5:7b` (7B, verified default) — `qwen3:latest` (8.2B, Q4_K_M, ~4.9 GB) available as optional experiment on RTX 3060 6 GB.
7|>
8|> *Last updated: 2026-05-31 | DeepEval 4.x*
9|
10|---
11|
12|## Table of Contents
13|
14|1. [Confident AI — Platform Integration](#1-confident-ai--platform-integration)
15|2. [Core Architecture Concepts](#2-core-architecture-concepts)
16|3. [Test Case Parameters — Complete Reference](#3-test-case-parameters--complete-reference)
17|4. [Metrics — All Categories](#4-metrics--all-categories)
18|5. [Configuration Objects](#5-configuration-objects)
19|6. [Environment Variables — Complete Reference](#6-environment-variables--complete-reference)
20|7. [CLI Commands](#7-cli-commands)
21|8. [Synthetic Data Generation](#8-synthetic-data-generation)
22|9. [EvaluationDataset API](#9-evaluationdataset-api)
23|10. [NPC Pipeline Recommendations](#10-npc-pipeline-recommendations)
24|11. [Troubleshooting Quick Reference](#11-troubleshooting-quick-reference)
25|12. [Quick Reference Code Snippets](#12-quick-reference-code-snippets)
26|13. [Evals REST API](#13-evals-rest-api)
27|14. [Remote Red Teaming and Security](#14-remote-red-teaming-and-security)
28|15. [CI/CD Integration](#15-cicd-integration)
29|16. [Monitoring and Alerting](#16-monitoring-and-alerting)
30|17. [Data Privacy and Compliance](#17-data-privacy-and-compliance)
31|18. [Scheduled Assessments](#18-scheduled-assessments)
32|
33|---
34|
35|## 1. Confident AI — Platform Integration
36|
37|Confident AI is the **optional cloud layer** for DeepEval. It provides hosted dashboards, experiment history, dataset versioning, and human annotation tooling. DeepEval runs fully locally without it.
38|
39|### Key Insight
40|
41|**You do not need to create an "AI app" or register a project on Confident AI.** Authentication is key-based only. No special policy configuration, project registration, or onboarding flow is required.
42|
43|### Setup
44|
45|```bash
46|# Option A: Environment variable (recommended for CI/pipeline)
47|export CONFIDENT_API_KEY="confident_us_..."
48|
49|# Option B: Interactive login (stores to ~/.deepeval/config.json)
50|deepeval login
51|
52|# EU data residency
53|export CONFIDENT_BASE_URL="https://eu.api.confident-ai.com"
54|```
55|
56|### What Confident AI Provides
57|
58|| Feature | How to Use | Status |
59||---------|-----------|--------|
60|| Eval dashboards | Auto-upload when `CONFIDENT_API_KEY` is set | ✅ Automatic |
61|| Run history & comparison | Pushes after each `deepeval test run` | ✅ Automatic |
62|| Dataset management | `EvaluationDataset.push(alias=...)` | ✅ Opt-in |
63|| Human annotations | Annotate on app.confident-ai.com | 🔜 Manual |
64|| Experiment comparison | Confident AI web UI after pushing results | 🔜 Manual |
65|
66|### Tracing / Monitoring
67|
68|The `@observe` decorator sends traces asynchronously to Confident AI (and stores locally in `.deepeval/`):
69|
70|```python
71|from deepeval import observe
72|from deepeval.tracing import Workflow
73|
74|@observe(name="npc_pipeline", capture_trace=True)
75|def run_agent(input: str) -> str:
76|    # Auto-traced
77|    ...
78|```
79|
80|Traces are flushed asynchronously. For CI exit guarantees, set:
81|```bash
82|export DEEPEVAL_TRACE_FLUSH=1
83|```
84|
85|### Offline-Only Mode
86|
87|No setup needed. Without `CONFIDENT_API_KEY`, everything runs locally and results are written to `.deepeval/.latest_test_run.json`.
88|
89|[⤴ back to TOC](#table-of-contents)
90|
91|---
92|
93|## 2. Core Architecture Concepts
94|
95|```
96|Test Cases ──→ Metrics ──→ Evaluation ──→ Results
97|                                              ↓
98|                                    Confident AI (optional)
99|```
100|
101|### Test Cases vs Metrics vs EvaluationDataset
102|
103|| Concept | Role |
104||---------|------|
105|| **LLMTestCase** | A single input/output pair to evaluate. Contains `input`, `actual_output`, and optional reference fields. |
106|| **Metric** | A scoring function applied to a test case. Returns a score (0–1) and optional reason. |
107|| **EvaluationDataset** | A collection of test cases (as `Golden` objects) that can be iterated, pushed/pulled from Confident AI, and fed to `evaluate()`. |
108|
109|### Evaluation Modes
110|
111|| Mode | API | Description |
112||------|-----|-------------|
113|| **Single-turn** | `LLMTestCase` | One input → one output. Used for dataset quality gates. |
114|| **Multi-turn (Conversational)** | `ConversationalTestCase` | Sequence of turns. Used for NPC dialogue evaluation. |
115|| **Arena** | Multiple `LLMTestCase` sets | Side-by-side model comparison with Elo scoring. |
116|
117|### LLM-as-a-Judge
118|
119|**All built-in DeepEval metrics use LLM-as-a-judge internally.** The judge model scores outputs against criteria without ground-truth data. This is what makes DeepEval powerful for NPC evaluation — you don't need pre-written answer keys.
120|
121|[⤴ back to TOC](#table-of-contents)
122|
123|---
124|
125|## 3. Test Case Parameters — Complete Reference
126|
127|### LLMTestCase (9 parameters)
128|
129|| Parameter | Type | Required By | Description |
130||-----------|------|-------------|-------------|
131|| `input` | `str` | **All metrics** | User query / prompt |
132|| `actual_output` | `str` | **All metrics** | LLM response |
133|| `expected_output` | `str` (optional) | Reference-based metrics (GEval, ExactMatch) | Ground truth answer |
134|| `context` | `List[str]` (optional) | HallucinationMetric, FaithfulnessMetric | Static knowledge base context |
135|| `retrieval_context` | `List[str]` (optional) | RAG metrics | Dynamically retrieved chunks |
136|| `tools_called` | `List[ToolCall]` (optional) | Agent metrics | Tools actually invoked |
137|| `expected_tools` | `List[ToolCall]` (optional) | ToolCorrectnessMetric | Tools that should have been used |
138|| `token_cost` | `float` (optional) | Cost tracking | Token cost of the interaction |
139|| `completion_time` | `float` (optional) | Latency tracking | Response time in seconds |
140|
141|*Additional optional fields:* `name` (str), `metadata` (dict), `tags` (list[str]), `comments` (list[Comment]), `retrieval_context` (replaces context for RAG flows).
142|
143|### ToolCall (5 parameters)
144|
145|| Parameter | Type | Description |
146||-----------|------|-------------|
147|| `name` | `str` (**required**) | Tool name |
148|| `description` | `str` (optional) | Tool purpose |
149|| `reasoning` | `str` (optional) | Why agent chose this tool |
150|| `output` | `Any` (optional) | Tool return value |
151|| `input_parameters` | `Dict[str, Any]` (optional) | Arguments passed |
152|
153|### ConversationalTestCase
154|
155|Wraps a list of message turns:
156|
157|```python
158|from deepeval.test_case import ConversationalTestCase, Message
159|
160|messages = [
161|    Message(role="user", content="Hello"),
162|    Message(role="assistant", content="Greetings, traveler!"),
163|    Message(role="user", content="Tell me about alchemy."),
164|    Message(role="assistant", content="Alchemy is the ancient practice of..."),
165|]
166|convo_test = ConversationalTestCase(messages=messages, name="npc_greeting")
167|```
168|
169|### Golden
170|
171|Lightweight test case template used in `EvaluationDataset`:
172|
173|```python
174|from deepeval.dataset import Golden
175|
176|golden = Golden(
177|    input="What is alchemy?",
178|    actual_output="Alchemy is...",
179|    expected_output="Alchemy is the ancient practice of...",
180|    context=["Reference doc text..."],
181|    retrieval_context=["Chunk 1..."],
182|    tools_called=[],
183|    additional_metadata={"npc_key": "alchemy_master", "category": "teaching"}
184|)
185|```
186|
187|[⤴ back to TOC](#table-of-contents)
188|
189|---
190|
191|## 4. Metrics — All Categories
192|
193|### 4.1 RAG Metrics (6)
194|
195|| Metric | Required Params | Score Direction | Default Threshold | Description |
196||--------|----------------|-----------------|-------------------|-------------|
197|| `FaithfulnessMetric` | `input`, `actual_output`, `retrieval_context` | Higher better | 0.5 | Factual consistency with retrieval context |
198|| `AnswerRelevancyMetric` | `input`, `actual_output` | Higher better | 0.5 | Output relevance to query |
199|| `ContextualRecallMetric` | `input`, `retrieval_context`, `expected_output` | Higher better | 0.5 | Context coverage of expected answer |
200|| `ContextualPrecisionMetric` | `input`, `retrieval_context`, `expected_output` | Higher better | 0.5 | Context ranking quality (relevant first) |
201|| `ContextualRelevancyMetric` | `input`, `retrieval_context` | Higher better | 0.5 | Fraction of context relevant to query |
202|| `HallucinationMetric` | `input`, `actual_output`, `context` | **Lower better** | 0.5 | Detects unsupported claims |
203|
204|**Common config params** (apply to all metrics):
205|
206|| Parameter | Type | Default | Description |
207||-----------|------|---------|-------------|
208|| `threshold` | `float` | `0.5` | Pass/fail boundary |
209|| `model` | `str` or `DeepEvalBaseLLM` | `None` | Judge model override |
210|| `include_reason` | `bool` | `True` | Include scoring reason in output |
211|| `async_mode` | `bool` | `True` | Run asynchronously (much faster) |
212|| `strict_mode` | `bool` | `False` | Enforce binary score (0 or 1) |
213|| `verbose_mode` | `bool` | `False` | Detailed logging |
214|
215|**Faithfulness-specific params:**
216|
217|| Parameter | Type | Default | Description |
218||-----------|------|---------|-------------|
219|| `truths_extraction_limit` | `int` | `10` | Max claims to check |
220|| `penalize_ambiguous_claims` | `bool` | `False` | Penalize claims not clearly supported |
221|
222|### 4.2 Agentic Metrics (6)
223|
224|| Metric | Description |
225||--------|-------------|
226|| `ToolCorrectnessMetric` | Tool selection accuracy vs `expected_tools` |
227|| `ToolUseMetric` | Tool calling accuracy (general) |
228|| `ArgumentCorrectnessMetric` | Argument precision in tool calls |
229|| `PlanAdherenceMetric` | Adherence to generated plans |
230|| `PlanQualityMetric` | Step-by-step reasoning quality |
231|| `GoalAccuracyMetric` | Goal achievement score |
232|| `TaskCompletionMetric` | Task completion (needs trace data) |
233|| `PromptAlignmentMetric` | Alignment with system prompt |
234|| `StepEfficiencyMetric` | Step count optimality |
235|
236|### 4.3 Conversational (Multi-turn) Metrics (5)
237|
238|| Metric | Description |
239||--------|-------------|
240|| `RoleAdherenceMetric` | Stays in character throughout conversation |
241|| `KnowledgeRetentionMetric` | Retains info across turns |
242|| `ConversationCompletenessMetric` | Satisfies user needs across full exchange |
243|| `ConversationRelevancyMetric` | Outputs relevant to each turn's input |
244|| `TopicAdherenceMetric` | Stays on topic |
245|
246|**Per-turn variants** (wrap in `TurnTestCase`):
247|
248|| Metric | Description |
249||--------|-------------|
250|| `TurnFaithfulnessMetric` | Factual consistency per turn |
251|| `TurnRelevancyMetric` | Relevance per turn |
252|| `TurnContextualPrecisionMetric` | Context quality per turn |
253|| `TurnContextualRecallMetric` | Coverage per turn |
254|| `TurnContextualRelevancyMetric` | Relevance per turn context |
255|
256|### 4.4 Safety Metrics (6)
257|
258|| Metric | Description |
259||--------|-------------|
260|| `BiasMetric` | Detects biased opinions |
261|| `ToxicityMetric` | Identifies toxic content |
262|| `NonAdviceMetric` | Ensures appropriate refusal |
263|| `MisuseMetric` | Detects capability misuse |
264|| `PIILeakageMetric` | Detects PII exposure |
265|| `RoleViolationMetric` | Role boundary violations |
266|
267|### 4.5 Non-LLM Metrics
268|
269|| Metric | Description |
270||--------|-------------|
271|| `ExactMatchMetric` | String exact match against `expected_output` |
272|| `PatternMatchMetric` | Regex pattern matching |
273|| `JsonCorrectnessMetric` | JSON schema compliance |
274|
275|### 4.6 Other Metrics
276|
277|| Metric | Description |
278||--------|-------------|
279|| `SummarizationMetric` | Alignment + coverage of summaries |
280|| `RagasMetric` | Wraps the Ragas evaluation framework |
281|
282|### 4.7 Custom Metrics (3 approaches)
283|
284|#### G-Eval (Recommended for NPC-specific criteria)
285|
286|```python
287|from deepeval.metrics import GEval
288|from deepeval.test_case import LLMTestCaseParams
289|
290|metric = GEval(
291|    name="NPC Personality Consistency",
292|    criteria=(
293|        "Determine if the NPC response stays in character based on the system prompt. "
294|        "Penalize responses that break character, use modern references inconsistent "
295|        "with the persona, or fail to reflect the NPC's voice and mannerisms."
296|    ),
297|    evaluation_params=[
298|        LLMTestCaseParams.INPUT,
299|        LLMTestCaseParams.ACTUAL_OUTPUT,
300|        LLMTestCaseParams.CONTEXT,
301|    ],
302|    model=JUDGE_MODEL,
303|    threshold=0.75,
304|    async_mode=True,
305|)
306|```
307|
308|#### DAG (Decision graph for objective criteria)
309|
310|Use for multi-step logical checks where a single G-Eval prompt isn't enough. Build a directed acyclic graph of evaluation nodes.
311|
312|#### BaseMetric Subclass (Full control)
313|
314|Subclass `BaseMetric` for complete custom logic:
315|
316|```python
317|from deepeval.metrics import BaseMetric
318|from deepeval.scorer import bleu_scorer, rouge_scorer
319|
320|class MyCustomMetric(BaseMetric):
321|    def __init__(self, threshold=0.5):
322|        self.threshold = threshold
323|        self.name = "My Custom Metric"
324|
325|    def measure(self, test_case) -> float:
326|        # Custom scoring logic
327|        score = ...
328|        self.success = score >= self.threshold
329|        return score
330|
331|    async def a_measure(self, test_case) -> float:
332|        return self.measure(test_case)
333|
334|    def is_successful(self) -> bool:
335|        return self.success
336|```
337|
338|[⤴ back to TOC](#table-of-contents)
339|
340|---
341|
342|## 5. Configuration Objects
343|
344|### AsyncConfig (3 params)
345|
346|Controls concurrent evaluation behavior — **critical for VRAM-limited setups**.
347|
348|| Parameter | Type | Default | Description |
349||-----------|------|---------|-------------|
350|| `max_concurrent` | `int` | `20` | Max parallel test cases |
351|| `run_async` | `bool` | `True` | Enable async evaluation |
352|| `throttle_value` | `float` | `0` | Seconds delay between cases (rate limiting) |
353|
354|```python
355|from deepeval import AsyncConfig
356|
357|# Safe for RTX 3060 6 GB — 4 concurrent instead of default 20
358|config = AsyncConfig(max_concurrent=4, run_async=True)
359|deepeval.set_async_config(config)
360|```
361|
362|### DisplayConfig (10 params)
363|
364|Controls terminal and file output.
365|
366|| Parameter | Type | Default | Description |
367||-----------|------|---------|-------------|
368|| `show_indicator` | `bool` | `True` | Progress indicator |
369|| `print_results` | `bool` | `True` | Print each result |
370|| `verbose_mode` | `bool` | `None` | Override per-metric verbose |
371|| `display` | `str` | `"all"` | Filter: `"all"`, `"failing"`, `"passing"` |
372|| `results_folder` | `str` | `None` | Persist `test_run_*.json` to dir |
373|| `results_subfolder` | `str` | `None` | Nested subfolder under results |
374|| `truncate_passing_cases` | `bool` | `True` | Truncate terminal output |
375|| `inspect_after_run` | `bool` | `True` | Prompt to open TUI |
376|| `file_type` | `str` | `None` | Export format: `"html"` or `"md"` |
377|| `file_output_dir` | `str` | `None` | Where to write exported file |
378|
379|```python
380|from deepeval import DisplayConfig
381|
382|deepeval.set_display_config(DisplayConfig(
383|    display="failing",
384|    results_folder="eval/results/deepeval",
385|    file_type="html",
386|    file_output_dir="eval/reports",
387|))
388|```
389|
390|### ErrorConfig (2 params)
391|
392|| Parameter | Type | Default | Description |
393||-----------|------|---------|-------------|
394|| `skip_on_missing_params` | `bool` | `False` | Skip cases with missing params |
395|| `ignore_errors` | `bool` | `False` | Ignore metric execution errors |
396|
397|### CacheConfig (2 params)
398|
399|| Parameter | Type | Default | Description |
400||-----------|------|---------|-------------|
401|| `use_cache` | `bool` | `False` | Use cached results |
402|| `write_cache` | `bool` | `True` | Write results to disk |
403|
404|[⤴ back to TOC](#table-of-contents)
405|
406|---
407|
408|## 6. Environment Variables — Complete Reference
409|
410|### General
411|
412|| Variable | Values | Effect |
413||----------|--------|--------|
414|| `CONFIDENT_API_KEY` | string | Enables cloud uploads to Confident AI |
415|| `CONFIDENT_BASE_URL` | URL | EU data residency endpoint (`https://eu.api.confident-ai.com`) |
416|| `CONFIDENT_OPEN_BROWSER` | `"true"` / `"false"` | Auto-open browser after run (default: `"true"`) |
417|| `DEEPEVAL_DISABLE_DOTENV` | `"1"` | Disable auto `.env` loading |
418|| `ENV_DIR_PATH` | path | Dotenv directory (default: CWD) |
419|| `APP_ENV` | string | Load `.env.{APP_ENV}` |
420|| `DEEPEVAL_RESULTS_FOLDER` | path | Save `test_run_*.json` locally |
421|| `DEEPEVAL_FILE_SYSTEM` | `"READ_ONLY"` | Restrict writes |
422|| `DEEPEVAL_DEFAULT_SAVE` | `"dotenv"[:path]` | Default save target for CLI |
423|| `DEEPEVAL_NO_INSPECT_PROMPT` | `"1"` | Disable inspect prompt in CI |
424|
425|### Model Provider Settings
426|
427|| Variable | Effect |
428||----------|--------|
429|| `USE_OLLAMA` | `"1"` / `"0"` — Use Ollama as judge |
430|| `OLLAMA_MODEL_NAME` | Model name (e.g., `qwen3:latest`) |
431|| `OLLAMA_API_BASE` | Ollama endpoint URL |
432|| `DEEPEVAL_OLLAMA_MODEL` | Judge model override (injected by `dataset_eval.py`) |
433|| `DEEPEVAL_OLLAMA_BASE_URL` | Ollama base URL (default: `http://localhost:11434`) |
434|| `DEEPEVAL_OLLAMA_TEMPERATURE` | Judge temperature (default: `0`) |
435|| `DEEPEVAL_OLLAMA_THINK` | Enable thinking tokens for reasoning models |
436|| `USE_OPENAI` / `OPENAI_API_KEY` | OpenAI provider |
437|| `USE_AZURE_OPENAI` / `AZURE_OPENAI_API_KEY` | Azure provider |
438|| `USE_GEMINI` / `GEMINI_API_KEY` | Gemini provider |
439|| `USE_ANTHROPIC` / `ANTHROPIC_API_KEY` | Anthropic provider |
440|| `USE_LITELLM` | LiteLLM provider |
441|| `USE_DEEPSEEK` / `DEEPSEEK_API_KEY` | DeepSeek provider |
442|
443|### Display & Logging
444|
445|| Variable | Effect |
446||----------|--------|
447|| `DEEPEVAL_LOG_LEVEL` | Log level (default: `INFO`) |
448|| `DEEPEVAL_IGNORE_LOGGING` | Suppress deepeval logs |
449|| `DEEPEVAL_DISABLE_COLORED` | Disable colored output |
450|
451|### Retry / Backoff (for API-based judges)
452|
453|| Variable | Type | Default |
454||----------|------|---------|
455|| `DEEPEVAL_RETRY_MAX_ATTEMPTS` | `int` | `2` |
456|| `DEEPEVAL_RETRY_INITIAL_SECONDS` | `float` | `1.0` |
457|| `DEEPEVAL_RETRY_EXP_BASE` | `float` | `2.0` |
458|| `DEEPEVAL_RETRY_JITTER` | `float` | `2.0` |
459|| `DEEPEVAL_RETRY_CAP_SECONDS` | `float` | `5.0` |
460|
461|### Timeouts & Concurrency
462|
463|| Variable | Effect |
464||----------|--------|
465|| `DEEPEVAL_API_TIMEOUT` | API call timeout (seconds) |
466|| `DEEPEVAL_MAX_CONCURRENT` | Override default max_concurrent |
467|
468|### Telemetry
469|
470|| Variable | Effect |
471||----------|--------|
472|| `DEEPEVAL_DISABLE_TELEMETRY` | Opt out of usage telemetry |
473|| `DEEPEVAL_TRACE_FLUSH` | Set to `"1"` to force flush traces before exit |
474|
475|### Our Pipeline Env Vars (Project-Specific)
476|
477|| Variable | Set By | Effect |
478||----------|--------|--------|
479|| `DEEPEVAL_DATASET_LIVE` | `dataset_eval.py` | Activates dataset quality evaluation |
480|| `DEEPEVAL_DATASET_NPC_KEYS` | `dataset_eval.py` | Comma-separated NPC keys to evaluate |
481|| `DEEPEVAL_DATASET_CATEGORIES` | `dataset_eval.py` | Comma-separated categories to evaluate |
482|| `DEEPEVAL_DATASET_TECHNIQUE` | `dataset_eval.py` | Dataset technique (template, ollama, etc.) |
483|| `DEEPEVAL_DATASET_CASES_PER_CATEGORY` | `dataset_eval.py` | Cases per category (default: 1) |
484|| `DEEPEVAL_JUDGE_PROVIDER` | `metrics.py` | Judge provider (`"ollama"` or `"wandb"`) |
485|| `DEEPEVAL_WANDB_MODEL` | `metrics.py` | W&B inference model name |
486|| `DEEPEVAL_WANDB_ENTITY` | `metrics.py` | W&B entity |
487|| `DEEPEVAL_WANDB_PROJECT` | `metrics.py` | W&B project |
488|
489|[⤴ back to TOC](#table-of-contents)
490|
491|---
492|
493|## 7. CLI Commands
494|
495|### `deepeval test run` — Primary command
496|
497|```bash
498|deepeval test run tests/evals/test_file.py [options]
499|```
500|
501|| Flag | Short | Description |
502||------|-------|-------------|
503|| `--verbose` | `-v` | Verbose output |
504|| `--exit-on-first-failure` | `-x` | Stop on first failure |
505|| `--show-warnings` | `-w` | Show pytest warnings |
506|| `--identifier` | `-id` | Label for this run (displayed in Confident AI) |
507|| `--num-processes` | `-n` | Parallel processes (uses pytest-xdist) |
508|| `--repeat` | `-r` | Repeat each test case N times |
509|| `--use-cache` | `-c` | Use cached results |
510|| `--ignore-errors` | `-i` | Continue on deepeval errors |
511|| `--skip-on-missing-params` | `-s` | Skip cases with missing params |
512|| `--display` | `-d` | Filter display: `all`, `failing`, `passing` |
513|| `--mark` | `-m` | pytest marker expression |
514|
515|**Our pipeline usage:**
516|
517|```bash
518|# Dataset quality gate (fast mode)
519|DEEPEVAL_DATASET_LIVE=1 \
520|DEEPEVAL_DATASET_NPC_KEYS="history_guide" \
521|DEEPEVAL_DATASET_TECHNIQUE="template" \
522|DEEPEVAL_DATASET_CASES_PER_CATEGORY=1 \
523|deepeval test run tests/evals/test_dataset_generation_quality.py \
524|  -id "history_guide-template-20260531" \
525|  -s \
526|  -i
527|
528|# Model quality eval
529|deepeval test run tests/evals/test_npc_model_quality.py \
530|  -id "history_guide-v2-candidate" \
531|  -s
532|```
533|
534|### `deepeval generate` — Synthetic data
535|
536|```bash
537|deepeval generate \
538|  --method docs \
539|  --variation single-turn \
540|  --documents ./data/npcs/reference_docs/ \
541|  --output-dir ./tests/evals/.dataset \
542|  --file-name .dataset
543|```
544|
545|| Flag | Options |
546||------|---------|
547|| `--method` | `docs`, `contexts`, `scratch`, `goldens` |
548|| `--variation` | `single-turn`, `multi-turn` |
549|| `--num-goldens` | `int` (default: `10`) |
550|| `--model` | Judge model for generation |
551|| `--max-concurrent` | `int` (default: `4`) |
552|
553|### Other Commands
554|
555|| Command | Description |
556||---------|-------------|
557|| `deepeval login` | Interactive Confident AI login |
558|| `deepeval logout` | Clear stored credentials |
559|| `deepeval view` | Open latest run in browser |
560|| `deepeval inspect` | TUI for trace browsing |
561|| `deepeval set-ollama --model qwen3:latest` | Set default Ollama judge model |
562|
563|[⤴ back to TOC](#table-of-contents)
564|
565|---
566|
567|## 8. Synthetic Data Generation
568|
569|### Golden Synthesizer
570|
571|Generate evaluation goldens from reference documents:
572|
573|```python
574|from deepeval.synthesizer import Synthesizer
575|
576|synthesizer = Synthesizer(model=judge_model)
577|goldens = synthesizer.generate_goldens(
578|    method="docs",
579|    documents=["data/npcs/reference_docs/history_guide_primer.md"],
580|    num_goldens=10,
581|    max_concurrent=4,
582|)
583|```
584|
585|**Methods:**
586|
587|| Method | Description |
588||--------|-------------|
589|| `docs` | Extract Q&A from documents |
590|| `contexts` | From provided context chunks |
591|| `scratch` | Generate from scratch (no documents) |
592|| `goldens` | Evolve existing goldens into new variants |
593|
594|**Styling flags** (per-context injection):
595|
596|| Flag | Effect |
597||------|--------|
598|| `--scenario-context` | Domain/context description |
599|| `--conversational-task` | Task description for multi-turn |
600|| `--conversational-style` | Tone guidance |
601|| `--conversational-difficulty` | Difficulty level (beginner/intermediate/advanced) |
602|| `--include-expected-output` | Include `expected_output` in goldens |
603|
604|### Conversation Simulator
605|
606|Generate multi-turn conversational data:
607|
608|```python
609|from deepeval.synthesizer import ConversationSimulator
610|
611|simulator = ConversationSimulator(model=judge_model)
612|conversations = simulator.simulate_conversations(
613|    max_turns=5,
614|    max_concurrent=4,
615|)
616|```
617|
618|[⤴ back to TOC](#table-of-contents)
619|
620|---
621|
622|## 9. EvaluationDataset API
623|
624|### Creation
625|
626|```python
627|from deepeval.dataset import EvaluationDataset, Golden
628|
629|# From list of goldens
630|dataset = EvaluationDataset(goldens=[
631|    Golden(input="...", actual_output="...", additional_metadata={"npc_key": "history_guide"}),
632|    Golden(input="...", actual_output="...", additional_metadata={"npc_key": "history_guide"}),
633|])
634|
635|# From file
636|dataset.add_goldens_from_json_file("goldens.json")
637|```
638|
639|### File Format (JSON)
640|
641|```json
642|[
643|  {
644|    "input": "What causes the seasons?",
645|    "actual_output": "The seasons are caused by...",
646|    "expected_output": "The tilt of Earth's axis...",
647|    "context": ["Reference text..."],
648|    "retrieval_context": ["Chunk 1..."],
649|    "additional_metadata": {"npc_key": "history_guide", "category": "teaching"}
650|  }
651|]
652|```
653|
654|### Push / Pull from Confident AI
655|
656|```python
657|# Push to cloud (tagged by alias)
658|dataset.push(
659|    alias="npc-goldens-history_guide-template",
660|    overwrite=True,
661|)
662|
663|# Pull from cloud
664|dataset.pull(
665|    alias="npc-goldens-history_guide-template",
666|    dataset_name="History Guide Template"
667|)
668|```
669|
670|### Evaluate
671|
672|```python
673|# Without tracing (batch evaluate)
674|from deepeval import evaluate
675|evaluate(test_cases=dataset, metrics=DATASET_QUALITY_METRICS)
676|
677|# With tracing (each case calls your agent)
678|for golden in dataset.evals_iterator(metrics=DATASET_QUALITY_METRICS):
679|    golden.actual_output = my_agent(golden.input)
680|```
681|
682|[⤴ back to TOC](#table-of-contents)
683|
684|---
685|
686|## 10. NPC Pipeline Recommendations
687|
688|### Architecture (How We Use It)
689|
690|```
691|Generate → Sanitize → [Dataset Quality Gate] → Train → Export → [Model Eval]
692|                          ↓                          ↓             ↓
693|                   DeepEval metrics            Dataset & GGUF   DeepEval +
694|                   (Faithfulness,             artifacts pushed  Confident AI
695|                    AnswerRelevancy,           to Confident      (RoleAdherence,
696|                    GEval persona)              (opt-in)         ConversationComplete)
697|```
698|
699|### Dataset Quality Gate (Pre-Training)
700|
701|Used in `src/core/dataset/dataset_eval.py`. Runs via `deepeval test run` subprocess.
702|
703|| Metric | Purpose | Threshold |
704||--------|---------|-----------|
705|| `GEval` ("Persona and Category Fit") | NPC stays in character, matches category | 0.75 |
706|| `GEval` ("Training Usefulness and Specificity") | Domain-specific, actionable content | 0.70 |
707|
708|**RAG metrics (optional, when reference docs are available):**
709|
710|| Metric | Purpose | Threshold |
711||--------|---------|-----------|
712|| `FaithfulnessMetric` | Factual consistency with reference docs | 0.85 |
713|| `AnswerRelevancyMetric` | Output relevance to query | 0.80 |
714|| `ContextualPrecisionMetric` | Context quality | 0.75 |
715|
716|**Judge model:**
717|
718|```python
719|from deepeval.models import OllamaModel
720|
721|judge = OllamaModel(
722|    model=os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen3:latest"),
723|    base_url=os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434"),
724|    temperature=0.0,
725|)
726|```
727|
728|### Model Evaluation (Post-Training)
729|
730|Used in `src/core/evaluation/evaluate.py` via `--deepeval` flag.
731|
732|| Metric | Purpose | Threshold |
733||--------|---------|-----------|
734|| `RoleAdherenceMetric` | Stays in character across turns | 0.80 |
735|| `KnowledgeRetentionMetric` | Retains info across turns | 0.80 |
736|| `ConversationCompletenessMetric` | Satisfies user needs fully | 0.70 |
737|| `ToxicityMetric` | No toxic content | 0.50 |
738|| `BiasMetric` | No biased statements | 0.50 |
739|
740|### VRAM-Safe Configuration (RTX 3060 6 GB)
741|
742|```python
743|from deepeval import AsyncConfig
744|
745|# Default max_concurrent is 20 — that will OOM on 6 GB
746|# Safe setting: 4 concurrent evaluations
747|config = AsyncConfig(
748|    max_concurrent=4,   # ← Override from default 20
749|    run_async=True,
750|)
751|```
752|
753|**Why 4:** Each concurrent evaluation loads the full Q4_K_M model (~4.9 GB weights + ~1 GB KV cache overhead). With 4 concurrent slots, Ollama's `OLLAMA_NUM_PARALLEL=4` setting handles them efficiently without exceeding VRAM.
754|
755|### Integration Pattern (Our Pipeline)
756|
757|```bash
758|# 1. Set judge model
759|export DEEPEVAL_OLLAMA_MODEL="qwen3:latest"
760|export DEEPEVAL_OLLAMA_BASE_URL="http://localhost:11434"
761|
762|# 2. Run smoke/dev template dataset gate (fast mode)
763|./ucore dataset-eval data/npcs/specs/history_guide.json \
764|  --technique template \
765|  --mode fast
766|
767|# 3. Smoke/dev train (bypass gate for iteration)
768|./ucore train data/npcs/specs/history_guide.json \
769|  --technique template \
770|  --preset fast-3b
771|
772|# 4. Evaluate with DeepEval
773|./ucore evaluate --baseline exports/history_guide/history_guide-lora-f16.gguf \
774|  --spec data/npcs/specs/history_guide.json \
775|  --deepeval \
776|  --deepeval-judge-model qwen3:latest
777|```
778|
779|[⤴ back to TOC](#table-of-contents)
780|
781|---
782|
783|## 11. Troubleshooting Quick Reference
784|
785|| Symptom | Cause | Fix |
786||---------|-------|-----|
787|| `No module named deepeval` | Not installed | `pip install -U deepeval` |
788|| `ImportError: deepeval.metrics` | Wrong version | `pip install "deepeval>=4.0"` |
789|| Confident upload not working | Missing/expired key | `deepeval login` or check `CONFIDENT_API_KEY` |
790|| Ollama judge not responding | Ollama not running | `ollama serve` |
791|| Ollama judge slow | Too many concurrent | Reduce `AsyncConfig(max_concurrent=2..4)` |
792|| VRAM OOM during eval | Too many parallel evals | Set `AsyncConfig(max_concurrent=2)` |
793|| Rate limit errors | Too many requests | Increase `throttle_value` or reduce `max_concurrent` |
794|| Metrics always score 0 | Wrong test case params | Check metric docs for required fields |
795|| Scores always 1.0 (trivially passing) | Threshold too low | Increase `threshold` or use `strict_mode=True` |
796|| Scores always 0.0 (trivially failing) | Threshold too high | Lower `threshold` or check if judge model is responding |
797|| `ContextualPrecisionMetric` errors | Missing `retrieval_context` | Pass `retrieval_context` (not just `context`) |
798|| `HallucinationMetric` errors | Missing `context` | Pass `context` (list of strings) |
799|| `DEEPEVAL_DATASET_LIVE` not triggering | Env not set | `export DEEPEVAL_DATASET_LIVE=1` before test run |
800|| Telemetry concerns | Want offline only | `DEEPEVAL_DISABLE_TELEMETRY=1` and no `CONFIDENT_API_KEY` |
801|| `.deepeval/` directory growing | Local cache | It's `.gitignore`d and regenerable |
802|| `deepeval view` not opening | No browser in CI | `deepeval inspect` for TUI, or read `.latest_test_run.json` |
803|| Metric returns `None` score | Judge model API error | Check Ollama logs, verify model is pulled |
804|| `ollama_think` not working with DeepEval | Custom model class needed | Use `DatasetJudgeOllamaModel` from `tests/evals/metrics.py` |
805|
806|### Common Judge Model Issues
807|
808|```
809|# Check Ollama is running
810|ollama ps
811|
812|# Check model is pulled
813|curl http://localhost:11434/api/tags
814|
815|# Test direct inference
816|curl http://localhost:11434/api/generate -d '{
817|  "model": "qwen3:latest",
818|  "prompt": "Hello",
819|  "stream": false
820|}'
821|
822|# Check VRAM usage
823|nvidia-smi
824|```
825|
826|[⤴ back to TOC](#table-of-contents)
827|
828|---
829|
830|## 12. Quick Reference Code Snippets
831|
832|### Snippet 1: Basic Metric — Single Test Case
833|
834|```python
835|from deepeval import evaluate
836|from deepeval.metrics import AnswerRelevancyMetric
837|from deepeval.test_case import LLMTestCase
838|from deepeval.models import OllamaModel
839|
840|judge = OllamaModel(model="qwen3:latest", temperature=0.0)
841|
842|test_case = LLMTestCase(
843|    input="What is the capital of France?",
844|    actual_output="The capital of France is Paris.",
845|)
846|
847|metric = AnswerRelevancyMetric(model=judge, threshold=0.5)
848|
849|evaluate([test_case], [metric])
850|```
851|
852|### Snippet 2: Dataset Evaluation (Multiple Cases)
853|
854|```python
855|from deepeval import evaluate
856|from deepeval.test_case import LLMTestCase
857|
858|test_cases = [
859|    LLMTestCase(input="Q1", actual_output="A1", context=["ctx"]),
860|    LLMTestCase(input="Q2", actual_output="A2", context=["ctx"]),
861|]
862|
863|results = evaluate(
864|    test_cases=test_cases,
865|    metrics=DATASET_QUALITY_METRICS,
866|)
867|# results contains per-case, per-metric scores
868|```
869|
870|### Snippet 3: With Tracing (evals_iterator + @observe)
871|
872|```python
873|from deepeval.dataset import EvaluationDataset, Golden
874|
875|dataset = EvaluationDataset(goldens=[Golden(input=q, ...) for q in queries])
876|
877|for golden in dataset.evals_iterator(metrics=DATASET_QUALITY_METRICS):
878|    golden.actual_output = my_llm_call(golden.input)
879|    # Metrics auto-calculated, results sent to Confident AI if configured
880|```
881|
882|### Snippet 4: Custom G-Eval for NPC Personality
883|
884|```python
885|from deepeval.metrics import GEval
886|from deepeval.test_case import LLMTestCaseParams
887|from deepeval.models import OllamaModel
888|
889|judge = OllamaModel(model="qwen3:latest", temperature=0.0)
890|
891|npc_personality = GEval(
892|    name="NPC Personality Consistency",
893|    criteria=(
894|        "Score how well the response reflects the NPC's established personality, "
895|        "voice, and mannerisms described in the system prompt. Penalize responses "
896|        "that sound generic, break character, or use anachronistic language."
897|    ),
898|    evaluation_params=[
899|        LLMTestCaseParams.INPUT,
900|        LLMTestCaseParams.ACTUAL_OUTPUT,
901|        LLMTestCaseParams.CONTEXT,
902|    ],
903|    model=judge,
904|    threshold=0.75,
905|    async_mode=True,
906|)
907|```
908|
909|### Snippet 5: AsyncConfig for VRAM-Limited Hardware
910|
911|```python
912|from deepeval import AsyncConfig, deepeval
913|
914|# RTX 3060 6 GB: 4 concurrent instead of default 20
915|deepeval.set_async_config(AsyncConfig(
916|    max_concurrent=4,
917|    run_async=True,
918|    throttle_value=0.1,  # 100ms between cases to smooth VRAM usage
919|))
920|
921|# For very tight VRAM (e.g., running Ollama + training simultaneously)
922|deepeval.set_async_config(AsyncConfig(
923|    max_concurrent=2,
924|    throttle_value=0.5,
925|))
926|```
927|
928|### Snippet 6: Saving Results Locally
929|
930|```python
931|from deepeval import deepeval
932|from deepeval import DisplayConfig
933|
934|deepeval.set_display_config(DisplayConfig(
935|    display="failing",
936|    results_folder="eval/results/deepeval",
937|    file_type="html",
938|    file_output_dir="eval/reports",
939|))
940|```
941|
942|### Snippet 7: Loading / Pushing Datasets via Confident
943|
944|```python
945|from deepeval.dataset import EvaluationDataset
946|import json
947|
948|# Load from file
949|with open("data/datasets/history_guide/template/train_clean.jsonl") as f:
950|    goldens = []
951|    for line in f:
952|        row = json.loads(line)
953|        messages = row.get("messages", [])
954|        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
955|        asst_msg = next((m["content"] for m in messages if m["role"] == "assistant"), "")
956|        goldens.append(Golden(
957|            input=user_msg,
958|            actual_output=asst_msg,
959|            additional_metadata={"npc_key": "history_guide", **row.get("metadata", {})},
960|        ))
961|
962|dataset = EvaluationDataset(goldens=goldens)
963|dataset.push(alias="npc-dataset-history_guide-template", overwrite=True)
964|```
965|
966|### Snippet 8: Reading Latest Results Programmatically
967|
968|```python
969|import json
970|from pathlib import Path
971|
972|latest_run = Path(".deepeval/.latest_test_run.json")
973|if latest_run.exists():
974|    data = json.loads(latest_run.read_text())
975|    print(f"Total: {data['total']}, Passed: {data['passed']}, Failed: {data['failed']}")
976|    for result in data.get("test_results", []):
977|        print(f"  {result['name']}: {result['score']} {'✅' if result['success'] else '❌'}")
978|```
979|
980|---
981|
982|> **Related docs:** [`ollama-local-performance.md`](ollama-local-performance.md) — judge tuning,
983|> [`training-workflow.md`](../training-workflow.md) — full pipeline integration,
984|> [`tests/evals/metrics.py`](../tests/evals/metrics.py) — our shared metric definitions,
985|> [`src/core/dataset/dataset_eval.py`](../src/core/dataset/dataset_eval.py) — quality gate entry point,
986|> [`cli-commands.md`](../reference/cli-commands.md) — all CLI flags for dataset-eval.
987|
988|[⤴ back to TOC](#table-of-contents)
989|
990|# Additions for deepeval-cheat-sheet.md
991|
992|Here are the proposed additions to enhance the `deepeval-cheat-sheet.md` file, based on the official Confident AI documentation.
993|
994|---
995|
996|## 13. Evals REST API
997|
998|While the `deepeval` Python library is the primary way to interact with Confident AI, a REST API is available for direct integration, especially in non-Python environments.
999|
1000|### API Quickstart
1001|
1002|- **Authentication**: The API uses Bearer token authentication.
1003|- **Data Models**: Core data models include `evaluations`, `datasets`, and `metrics`.
1004|- **API Conventions**: The API follows standard REST conventions with predictable response formats and status codes.
1005|
1006|For detailed information, refer to the [official API reference](https://www.confident-ai.com/docs/api-reference/introduction).
1007|
1008|---
1009|
1010|## 14. Remote Red Teaming and Security
1011|
1012|Confident AI provides a powerful platform for remote red teaming and security assessments, going beyond the local capabilities of `deepteam`.
1013|
1014|### Key Features
1015|
1016|- **Vulnerability Assessment**: Systematically identify weaknesses like bias, toxicity, PII leakage, and prompt injection vulnerabilities.
1017|- **Adversarial Testing**: Simulate real-world attacks using jailbreaking, prompt injection, and other sophisticated methods.
1018|- **Risk Profiling**: Comprehensive evaluation across 40+ vulnerability types with detailed risk assessments and remediation guidance.
1019|
1020|### Security Frameworks
1021|
1022|You can use pre-defined security frameworks for comprehensive assessments:
1023|- **OWASP Top 10 for LLMs**
1024|- **NIST AI RMF** (AI Risk Management Framework)
1025|- **MITRE ATLAS**
1026|
1027|These frameworks can be applied directly from the Confident AI platform or programmatically via `deepteam`.
1028|
1029|### Best Practices for Red Teaming
1030|
1031|1.  **Start with frameworks**: Use OWASP Top 10 or NIST AI RMF for comprehensive coverage.
1032|2.  **Test early and often**: Integrate red teaming into your development cycle.
1033|3.  **Focus on your use case**: Customize vulnerabilities based on your application’s risks.
1034|4.  **Monitor continuously**: Set up ongoing safety assessments for production systems.
1035|5.  **Document and remediate**: Keep detailed records of findings and remediation efforts.
1036|
1037|---
1038|
1039|## 15. CI/CD Integration
1040|
1041|Automate your quality and security assessments by integrating Confident AI into your CI/CD pipeline.
1042|
1043|### Recommendations
1044|
1045|- **Use environment variables**: Store your `CONFIDENT_API_KEY` as a secret in your CI/CD provider.
1046|- **Run evaluations on every pull request**: Catch regressions before they are merged.
1047|- **Use `deepeval test run` with the `-x` flag**: To exit on the first failure and fail the build.
1048|- **Integrate Red Teaming**: Use `deepteam` to run security assessments as part of your pipeline.
1049|- **Persist reports**: Use the `results_folder` and `file_output_dir` display configurations to save HTML or Markdown reports as artifacts of your CI/CD runs.
1050|
1051|---
1052|
1053|## 16. Monitoring and Alerting
1054|
1055|Confident AI's platform offers real-time monitoring and alerting to ensure the quality of your AI applications in production.
1056|
1057|### How it works
1058|
1059|- **Tracing**: The `@observe` decorator in the `deepeval` library sends traces of your AI application's executions to Confident AI.
1060|- **Real-time Evals**: Configure real-time evaluations on the platform to continuously monitor the quality of your application.
1061|- **Alerting**: Set up alerts to be notified via email or other channels when the quality of your AI application degrades.
1062|
1063|---
1064|
1065|## 17. Data Privacy and Compliance
1066|
1067|Confident AI is designed with data security in mind, offering features to meet enterprise-grade compliance requirements.
1068|
1069|### Key Features
1070|
1071|- **Encryption**: All data is encrypted at rest and protected by TLS in transit.
1072|- **SOC II Compliance**: Available for customers on the **Enterprise plan**.
1073|- **HIPAA Compliance**: Business Associate Agreements (BAAs) are available for customers on the **Premium Plan** as an add-on.
1074|
1075|For more details, refer to the [Data Handling documentation](https://www.confident-ai.com/docs/resources/data-handling).
1076|
1077|---
1078|
1079|## 18. Scheduled Assessments
1080|
1081|Automate your red teaming and risk assessments by scheduling them to run at regular intervals.
1082|
1083|### How to create a schedule
1084|
1085|1.  Navigate to the **Automations** tab in the Confident AI platform.
1086|2.  Click **Add Schedule** and choose your configuration.
1087|3.  Specify the interval for the assessments (e.g., daily, weekly).
1088|4.  Click **Create Schedule**.
1089|