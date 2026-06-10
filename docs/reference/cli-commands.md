1|1|# Unsloth_Core Commands & Flags Dictionary
2|2|
3|3|> **Exhaustive reference** of every CLI command, subcommand, flag, config key, preset,
4|4|> contract constant, and parameter across the entire Unsloth_Core pipeline.
5|5|>
6|6|> Generated from: `ucore` (1040 lines), 7 preset YAMLs, 4 config YAMLs,
7|7|> 6 Python source files.
8|8|
9|9|---
10|10|
11|11|## Table of Contents
12|12|
13|13|1. [CLI Commands (ucore subcommands)](#1-cli-commands-ucore-subcommands)
14|14|2. [Dataset Categories & Contract Constants](#2-dataset-categories--contract-constants)
15|15|3. [Generation Techniques](#3-generation-techniques)
16|16|4. [Ollama Model Presets](#4-ollama-model-presets)
17|17|5. [Training Presets](#5-training-presets)
18|18|6. [Training Parameters (from base YAML)](#6-training-parameters-from-base-yaml)
19|19|7. [Sanitize Settings](#7-sanitize-settings)
20|20|8. [Dataset Eval (DeepEval) Settings](#8-dataset-eval-deepeval-settings)
21|21|9. [Evaluation Settings (./ucore evaluate)](#9-evaluation-settings-ucore-evaluate)
22|22|10. [Feedback Loop Settings](#10-feedback-loop-settings)
23|23|11. [Preflight / Preheat Settings](#11-preflight--preheat-settings)
24|24|12. [Model Size → Preset Mapping](#12-model-size--preset-mapping)
25|25|13. [Workload Policy](#13-workload-policy)
26|26|14. [Promotion Rules](#14-promotion-rules)
27|27|15. [Export Settings](#15-export-settings)
28|28|16. [Engine / Inference Settings](#16-engine--inference-settings)
29|29|17. [W&B Settings](#17-wb-settings)
30|30|18. [CLI Global Flags](#18-cli-global-flags)
31|31|19. [Spec Validation Checks](#19-spec-validation-checks)
32|32|20. [Environment Variables](#20-environment-variables)
33|33|
34|34|---
35|35|
36|36|## 1. CLI Commands (ucore subcommands)
37|37|
38|38|Every subcommand registered on the `ucore` argparse root parser.
39|39|
40|40|### Global Flags (apply to every subcommand)
41|41|
42|42|| Flag | Type | Default | Description |
43|43||------|------|---------|-------------|
44|44|| `--workflow-hooks PATH` | `str` | `None` | Path to a JSONL hook log for step tracing (injected into `WORKFLOW_HOOKS_PATH` env) |
45|45|| `--watch` | `bool` | `False` | Stream command output with early error alerts and save a watch log (`UCORE_WATCH=1`) |
46|46|
47|47|---
48|48|
49|49|### `generate`
50|50|Generate dataset from a subject spec.
51|51|
52|52|| Flag | Type | Default | Choices |
53|53||------|------|---------|---------|
54|54|| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
55|55|| `--ollama` | `bool` | `False` | Shortcut for `--technique ollama` |
56|56|| `--technique` | `str` | `template` | `docs`, `ollama`, `template`, `openai`, `anthropic` |
57|57|| `--docs-manifest PATH` | `str` | — | Docs corpus manifest override for `--technique docs` |
58|58|| `--model MODEL` | `str` | — | LLM model name for ollama/openai/anthropic |
59|59|| `--concept-focus CAT` | `str[]` | — | Focus on specific categories (repeatable, boosts example count) |
60|60|| `--fresh` | `bool` | `False` | Ignore checkpoint recovery, regenerate from scratch |
61|61|| `--push-to-confident` | `bool` | `False` | Push generated dataset to Confident AI with alias `npc-dataset-{npc_key}-{technique}` |
62|62|
63|63|---
64|64|
65|65|### `generate-ollama`
66|66|Generate dataset using optimized Ollama generator (defaults to `qwen2.5:7b`).
67|67|
68|68|| Flag | Type | Default | Description |
69|69||------|------|---------|-------------|
70|70|| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
71|71|| `--model MODEL` | `str` | `qwen2.5:7b` | Ollama model |
72|72|| `--url URL` | `str` | `http://localhost:11434` | Ollama server URL |
73|73|| `--batch-size N` | `int` | `4` | Concurrent generation tasks |
74|74|| `--max-retries N` | `int` | `3` | Max retries per generation |
75|75|| `--temperature T` | `float` | `0.6` | Generation temperature |
76|76|| `--multi-turn-ratio T` | `float` | `0.25` | Fraction of rows to request as two-turn dialogues |
77|77|| `--seed N` | `int` | `42` | Random seed |
78|78|| `--output`, `-o PATH` | `str` | — | Output JSONL path |
79|79|| `--no-validation` | `bool` | `False` | Skip validation split |
80|80|| `--val-split T` | `float` | `0.12` | Validation split ratio |
81|81|| `--check-health` | `bool` | `False` | Verify Ollama is running |
82|82|| `--pull-model` | `bool` | `False` | Auto-pull model if not found |
83|83|| `--concept-focus CAT` | `str[]` | — | Focus regeneration on specific categories (repeatable) |
84|84|| `--dry-run` | `bool` | `False` | Show plan without generating |
85|85|| `--fresh` | `bool` | `False` | Ignore checkpoint recovery |
86|86|
87|87|---
88|88|
89|89|### `sanitize`
90|90|Sanitize a generated dataset (remove AI artifacts, fix formatting).
91|91|
92|92|| Flag | Type | Default | Description |
93|93||------|------|---------|-------------|
94|94|| `input` (positional) | `str` | *required* | Path to input JSONL |
95|95|| `--output`, `-o PATH` | `str` | `*_clean.jsonl` | Path to output JSONL |
96|96|| `--min-length N` | `int` | `10` | Min chars for assistant response |
97|97|| `--max-sentences N` | `int` | `5` | Max sentences for assistant response |
98|98|| `--verbose`, `-v` | `bool` | `False` | Print discarded examples and metadata warnings |
99|99|| `--spec PATH` | `str` | — | Path to NPC spec JSON (better quality scoring) |
100|100|| `--strict-canonical` | `bool` | `False` | Require canonical dataset path |
101|101|| `--strict-mode` | `bool` | `False` | Raise on structural validation errors instead of discarding |
102|102|| `--artifact-check` | `str` | `strict` | `strict`, `warn`, `off` |
103|103|| `--verbose-artifacts` | `bool` | `False` | Show exact artifact pattern matched |
104|104|| `--quality-threshold-pass N` | `int` | `70` | Minimum total score to pass |
105|105|| `--quality-threshold-flag N` | `int` | `50` | Below this total, examples flagged for review |
106|106|| `--quality-report` | `bool` | `False` | Print quality score distribution at end |
107|107|| `--discard-below-score N` | `int` | `0` | Discard examples below this total score (0 = keep all) |
108|108|| `--no-fix-metadata` | `bool` | `False` | Disable auto-repair of missing metadata fields |
109|109|| `--require-complete-metadata` | `bool` | `False` | Error out if any metadata field is missing |
110|110|| `--dedup` / `--no-dedup` | `bool` | `True` | Enable/disable content_hash deduplication |
111|111|| `--dedup-report` | `bool` | `False` | Show which content hashes removed during dedup |
112|112|| `--write-manifest` / `--no-write-manifest` | `bool` | `True` | Enable/disable enriched manifest writing |
113|113|| `--manifest-path PATH` | `str` | — | Override manifest output path |
114|114|| `--debug` | `bool` | `False` | Re-raise exceptions with traceback for debugging |
115|115|
116|116|---
117|117|
118|118|### `dataset-eval`
119|119|Run DeepEval quality checks on a generated dataset (quality gate).
120|120|
121|121|| Flag | Type | Default | Choices |
122|122||------|------|---------|---------|
123|123|| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
124|124|| `--technique TECH` | `str` | `template` | `docs`, `ollama`, `template`, `openai`, `anthropic` |
125|125|| `--judge-model MODEL` | `str` | *auto (presets)* | Local Ollama judge model |
126|126|| `--judge-preset PRESET` | `str` | *auto (presets)* | `judge-qwen25`, `judge-llama31-exp`, `judge-qwen35-exp`, `judge-qwen3-exp` |
127|127|| `--ollama-base-url URL` | `str` | `http://localhost:11434` | Ollama server URL |
128|128|| `--judge-temperature T` | `float` | `0.0` | Judge temperature |
129|129|| `--mode` | `str` | `fast` | `fast`, `release` |
130|130|| `--cases-per-category N` | `int` | *mode-dependent* | Rows sampled per category (1 for fast, 5 for release) |
131|131|| `--categories CATS` | `str` | — | Comma-separated category filter |
132|132|| `--identifier ID` | `str` | — | DeepEval run identifier |
133|133|| `--display` | `str` | `all` | `all`, `failing`, `passing` |
134|134|| `--ignore-errors` | `bool` | `False` | Continue when individual metric calls error |
135|135|| `--soft-fail` | `bool` | `False` | Write artifacts but return 0 even when metrics fail |
136|136|| `--output PATH` | `str` | — | Quality summary JSON path |
137|137|| `--wandb` | `bool` | `False` | Enable W&B logging |
138|138|| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
139|139|| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
140|140|| `--confident` | `bool` | `False` | Enforce that CONFIDENT_API_KEY is configured (exits with error if missing) |
141|141|
142|142|---
143|143|
144|144|### `train`
145|145|Train a model (LoRA SFT).
146|146|
147|147|| Flag | Type | Default | Description |
148|148||------|------|---------|-------------|
149|149|| `config_or_spec` (pos.) | `str` | *required* | Path to config YAML or subject spec |
150|150|| `--from-spec` | `bool` | `False` | Train directly from spec (auto when suffix is `.json`) |
151|151|| `--preset PRESET` | `str` | — | Training preset |
152|152|| `--technique TECH` | `str` | — | `docs`, `ollama`, `template`, `openai`, `anthropic` |
153|153|| `--model MODEL` | `str` | — | Base model ID/path override |
154|154|| `--export-gguf` | `bool` | `False` | Export to GGUF after training (adapter mode for Unity) |
155|155|| `--full-merge-export` | `bool` | `False` | Full merge export after training (slower, standalone GGUF) |
156|156|| `--wandb` | `bool` | *from config* | Enable W&B logging (overrides config) |
157|157|| `--no-wandb` | `bool` | — | Disable W&B logging (overrides config) |
158|158|| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
159|159|| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
160|160|| `--lr T` | `float` | — | Learning rate |
161|161|| `--batch-size N` | `int` | — | Batch size |
162|162|| `--epochs N` | `int` | — | Number of epochs |
163|163|| `--lora-r N` | `int` | — | LoRA rank |
164|164|| `--lora-alpha N` | `int` | — | LoRA alpha |
165|165|| `--lr-scheduler SCHED` | `str` | — | Learning rate scheduler type |
166|166|| `--allow-ungated-dataset` | `bool` | `False` | Train without a fresh passing dataset-eval artifact |
167|167|
168|168|---
169|169|
170|170|### `smoke`
171|171|Smoke test a GGUF model.
172|172|
173|173|| Flag | Type | Default | Description |
174|174||------|------|---------|-------------|
175|175|| `model` (positional) | `str` | *required* | Path to GGUF model |
176|176|| `--spec PATH` | `str` | — | Path to subject spec for context |
177|177|| `--check-integrity` | `bool` | `False` | Validate GGUF file structure (no inference) |
178|178|| `--track` | `bool` | `False` | Track results in Supabase |
179|179|
180|180|---
181|181|
182|182|### `validate-config`
183|183|Resolve and validate effective training config.
184|184|
185|185|| Flag | Type | Default | Description |
186|186||------|------|---------|-------------|
187|187|| `--spec PATH` | `str` | — | Path to subject spec JSON |
188|188|| `--config PATH` | `str` | — | Path to YAML config |
189|189|| `--preset PRESET` | `str` | — | Training preset |
190|190|| `--data PATH` | `str` | — | Training data path |
191|191|| `--model MODEL` | `str` | — | Model ID override |
192|192|| `--output PATH` | `str` | — | Output dir override |
193|193|| `--npc-key KEY` | `str` | — | NPC key when using `--config` |
194|194|| `--format` | `str` | `yaml` | `yaml`, `json` |
195|195|| `--strict` | `bool` | `False` | Treat warnings as errors |
196|196|| `--require-canonical` | `bool` | `False` | Require canonical dataset train path |
197|197|
198|198|---
199|199|
200|200|### `validate-spec`
201|201|Validate subject specs before generation/training.
202|202|
203|203|| Flag | Type | Default | Description |
204|204||------|------|---------|-------------|
205|205|| `spec` (positional, optional) | `str` | — | Path to subject spec JSON |
206|206|| `--all` | `bool` | `False` | Validate every `data/npcs/specs/*.json` spec |
207|207|| `--json` | `bool` | `False` | Output JSON |
208|208|| `--strict` | `bool` | `False` | Treat warnings as errors |
209|209|| `--require-reference-docs` | `bool` | `False` | Fail if `reference_doc` missing/unreadable |
210|210|| `--require-reference-contract` | `bool` | `False` | Fail unless `reference_doc` meets generation-readiness minimums |
211|211|| `--require-all-categories` | `bool` | `False` | Fail unless all 5 dataset categories have positive counts |
212|212|| `--require-dataset-minimums` | `bool` | `False` | Fail unless all categories meet minimum SFT counts |
213|213|| `--generation-ready` | `bool` | `False` | Fail unless spec is ready for fresh dataset generation |
214|214|
215|215|---
216|216|
217|217|### `export`
218|218|Export trained LoRA adapter to GGUF (adapter-only by default).
219|219|
220|220|| Flag | Type | Default | Description |
221|221||------|------|---------|-------------|
222|222|| `npc_key` (positional) | `str` | *required* | NPC key (snake_case) |
223|223|| `--model`, `-m MODEL` | `str` | *auto-detected* | Base model ID |
224|224|| `--quantization TYPE` | `str` | `q4_k_m` | GGUF quantization for full-merge mode |
225|225|| `--full-merge` | `bool` | `False` | Produce full merged GGUF (slower, standalone) |
226|226|| `--skip-f16` | `bool` | `False` | In full-merge mode: skip f16 variant |
227|227|| `--outtype TYPE` | `str` | `f16` | `f32`, `f16`, `bf16`, `q8_0` |
228|228|| `--maximum-memory GB` | `float` | — | Max memory (GB) for `save_pretrained_gguf` (full-merge) |
229|229|| `--resume` | `bool` | `False` | Skip GGUFs that already exist |
230|230|
231|231|---
232|232|
233|233|### `export-resume`
234|234|Resume/continue GGUF export for an NPC.
235|235|
236|236|| Flag | Type | Default | Description |
237|237||------|------|---------|-------------|
238|238|| `npc_key` (positional) | `str` | *required* | NPC key |
239|239|| `--model`, `-m MODEL` | `str` | — | Base model ID |
240|240|| `--quantization TYPE` | `str` | `q4_k_m` | GGUF quantization |
241|241|| `--skip-f16` | `bool` | `False` | Skip exporting f16 variant |
242|242|| `--timeout-seconds N` | `int` | `5400` | Per-variant timeout |
243|243|
244|244|---
245|245|
246|246|### `export-adapter`
247|247|Export LoRA adapter as GGUF (for LLMUnity).
248|248|
249|249|| Flag | Type | Default | Description |
250|250||------|------|---------|-------------|
251|251|| `adapter_path` (pos., optional) | `str` | — | Path to PEFT adapter directory |
252|252|| `--all`, `-a` | `bool` | `False` | Convert all adapters in `outputs/` |
253|253|| `--outtype TYPE` | `str` | `f16` | `f32`, `f16`, `bf16`, `q8_0`, `auto` |
254|254|| `--outfile PATH` | `str` | — | Explicit output file path |
255|255|
256|256|---
257|257|
258|258|### `deploy`
259|259|Deploy exports to Unity project.
260|260|
261|261|| Flag | Type | Default | Description |
262|262||------|------|---------|-------------|
263|263|| `--unity-project`, `-u PATH` | `str` | *auto-detected* | Path to Unity project |
264|264|| `--dry-run` | `bool` | `False` | Show what would be done without copying |
265|265|| `--skip-export` | `bool` | `False` | Skip GGUF export step |
266|266|| `--export-only` | `bool` | `False` | Only export, skip Unity copy |
267|267|
268|268|---
269|269|
270|270|### `evaluate`
271|271|Compare two GGUF models side-by-side with optional LLM judge.
272|272|
273|273|| Flag | Type | Default | Description |
274|274||------|------|---------|-------------|
275|275|| `--baseline PATH` | `str` | — | Baseline GGUF model path |
276|276|| `--candidate PATH` | `str` | — | Candidate GGUF model path |
277|277|| `--model`, `-m PATH` | `str` | — | Single model GGUF path (interactive) |
278|278|| `--spec`, `-s PATH` | `str` | — | Subject spec JSON |
279|279|| `--val-data PATH` | `str` | — | Validation JSONL path |
280|280|| `--num-questions N` | `int` | `10` | Number of eval questions |
281|281|| `--output`, `-o PATH` | `str` | — | Output report path |
282|282|| `--report-html` | `bool` | `False` | Generate HTML report with charts |
283|283|| `--judge` | `bool` | `False` | Use local Ollama judge |
284|284|| `--judge-model MODEL` | `str` | `qwen2.5:7b` | Judge model |
285|285|| `--track` | `bool` | `False` | Track results in `eval/results/` |
286|286|| `--wandb` | `bool` | `False` | Enable W&B evaluation tracking |
287|287|| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
288|288|| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
289|289|| `--interactive`, `-i` | `bool` | `False` | Interactive chat mode |
290|290|| `--port N` | `int` | `8888` | llama-server port |
291|291|| `--gpu-layers N` | `int` | `99` | GPU layers to offload (0 = CPU-only) |
292|292|| `--max-tokens N` | `int` | `256` | Max generated tokens per eval answer |
293|293|| `--feedback-json PATH` | `str` | — | Save structured per-concept eval results for feedback loop |
294|294|| `--base-model PATH` | `str` | — | Base GGUF path (required when `--candidate` is a LoRA adapter) |
295|295|| `--lora-weight T` | `float` | `1.0` | LoRA adapter weight |
296|296|| `--host ADDR` | `str` | `127.0.0.1` | llama-server host |
297|297|| `--training-metrics [PATH]` | `str` | — | Show training metrics from TensorBoard logs (optional: runs dir) |
298|298|| `--npc-key KEY` | `str` | — | NPC key for per-model TensorBoard runs lookup |
299|299|| `--deepeval` | `bool` | `False` | Run DeepEval model quality evaluation after conventional eval |
300|300|| `--deepeval-judge-model` | `str` | `qwen3:latest` | Ollama model to use as judge |
301|301|| `--deepeval-identifier` | `str` | — | Custom identifier for the DeepEval test run |
302|302|
303|303|---
304|304|
305|305|### `quick-eval`
306|306|Quick local evaluation (llama-cpp-python).
307|307|
308|308|| Flag | Type | Default | Description |
309|309||------|------|---------|-------------|
310|310|| `--adapter PATH` | `str` | *required* | Path to LoRA adapter directory |
311|311|| `--samples`, `-n N` | `int` | `20` | Number of validation samples |
312|312|| `--spec`, `-s PATH` | `str` | *required* | Subject spec JSON |
313|313|| `--val-data PATH` | `str` | *auto-detected* | Validation JSONL |
314|314|| `--output PATH` | `str` | `eval/results/{key}_eval_report.json` | Output report path |
315|315|| `--feedback-json PATH` | `str` | — | Save structured per-concept eval results |
316|316|
317|317|---
318|318|
319|319|### `track`
320|320|Track or show evaluation results.
321|321|
322|322|| Flag | Type | Default | Description |
323|323||------|------|---------|-------------|
324|324|| `--npc-key KEY` | `str` | — | NPC key |
325|325|| `--model PATH` | `str` | — | Model GGUF path |
326|326|| `--show` | `bool` | `False` | Show evaluation history |
327|327|| `--win-rate T` | `float` | — | Win rate vs baseline (0–1) |
328|328|| `--avg-quality T` | `float` | — | Average quality score |
329|329|| `--val-loss T` | `float` | — | Validation loss |
330|330|| `--notes TEXT` | `str` | `""` | Notes about this run |
331|331|
332|332|---
333|333|
334|334|### `compare-runs`
335|335|Compare two training runs by run_id.
336|336|
337|337|| Flag | Type | Default | Description |
338|338||------|------|---------|-------------|
339|339|| `npc_key` (positional) | `str` | *required* | NPC key |
340|340|| `--baseline-run ID` | `str` | *required* | Baseline run ID |
341|341|| `--candidate-run ID` | `str` | *required* | Candidate run ID |
342|342|| `--spec PATH` | `str` | *auto-detected* | Subject spec |
343|343|| `--num-questions N` | `int` | `10` | Number of eval questions |
344|344|| `--judge` | `bool` | `False` | Use local Ollama judge |
345|345|
346|346|---
347|347|
348|348|### `feedback`
349|349|Run the self-improving feedback loop.
350|350|
351|351|| Flag | Type | Default | Description |
352|352||------|------|---------|-------------|
353|353|| `feedback_json` (pos.) | `str` | *required* | Path to feedback JSON from `evaluate --feedback-json` |
354|354|| `--win-rate-threshold T` | `float` | `0.5` | Min win rate |
355|355|| `--quality-threshold T` | `float` | `25.0` | Max quality score (lower = better) |
356|356|| `--violation-threshold N` | `int` | `1` | Max constraint violations |
357|357|| `--dry-run` | `bool` | `False` | Analyze without regenerating |
358|358|| `--auto`, `-y` | `bool` | `False` | Auto-accept all suggestions |
359|359|| `--skip-gap-detection` | `bool` | `False` | Skip knowledge coverage check |
360|360|| `--save-gaps PATH` | `str` | — | Save knowledge gap report to JSON |
361|361|| `--json` | `bool` | `False` | Output machine-readable JSON summary |
362|362|| `--auto-retrain` | `bool` | `False` | After regeneration, auto-retrain and re-evaluate |
363|363|| `--train-preset PRESET` | `str` | `fast-3b` | Training preset for auto-retrain |
364|364|| `--baseline PATH` | `str` | — | Baseline GGUF for auto-evaluation after retrain |
365|365|| `--regeneration-technique TECH` | `str` | `template` | `template`, `ollama` |
366|366|| `--regeneration-preset PRESET` | `str` | *auto (presets)* | `generate-qwen25`, `generate-llama31`, `generate-qwen35-exp`, `generate-qwen3-exp` |
367|367|| `--regeneration-model MODEL` | `str` | `qwen2.5:7b` | Exact Ollama regeneration model (wins over preset) |
368|368|| `--regeneration-url URL` | `str` | `http://localhost:11434` | Ollama base URL for regeneration |
369|369|| `--regeneration-batch-size N` | `int` | `4` | Ollama batch size for regeneration |
370|370|| `--deepeval-judge-preset PRESET` | `str` | *auto (presets)* | `judge-qwen25`, `judge-llama31-exp`, `judge-qwen35-exp`, `judge-qwen3-exp` |
371|371|| `--deepeval-judge-model MODEL` | `str` | — | Exact Ollama judge model (wins over preset) |
372|372|| `--deepeval-ollama-url URL` | `str` | `http://localhost:11434` | Ollama base URL for DeepEval |
373|373|| `--deepeval-cases-per-category N` | `int` | `1` | Cases per category for fast DeepEval |
374|374|| `--deepeval-soft-fail` | `bool` | `False` | Do not abort dataset eval on metric failure |
375|375|| `--wandb` | `bool` | `False` | Enable W&B logging |
376|376|| `--wandb-project NAME` | `str` | `unsloth-core` | W&B project |
377|377|| `--wandb-entity ENTITY` | `str` | *auto-detect* | W&B entity |
378|378|
379|379|---
380|380|
381|381|### `pipeline`
382|382|Run the full canonical pipeline: validate-spec → generate → sanitize → dataset-eval → train → export → smoke-test → evaluate.
383|383|
384|384|| Flag | Type | Default | Description |
385|385||------|------|---------|-------------|
386|386|| `spec` (positional) | `str` | *required* | Path to subject spec JSON |
387|387|| `--preset PRESET` | `str` | `fast-3b` | Training preset |
388|388|| `--ollama` | `bool` | `False` | Shortcut for `--technique ollama` |
389|389|| `--technique TECH` | `str` | `template` | `docs`, `ollama`, `template`, `openai`, `anthropic` |
390|390|| `--docs-manifest PATH` | `str` | — | Docs corpus manifest for `--technique docs` |
391|391|| `--model MODEL` | `str` | — | LLM model name for generation stage |
392|392|| `--track` | `bool` | `False` | Track results in Supabase |
393|393|| `--wandb` | `bool` | `False` | Enable W&B logging during training |
394|394|| `--full-merge-export` | `bool` | `False` | Full merge export (standalone GGUF) |
395|395|| `--skip-smoke` | `bool` | `False` | Skip smoke test phase |
396|396|| `--skip-eval` | `bool` | `False` | Skip evaluation phase |
397|397|| `--skip-spec-validate` | `bool` | `False` | Skip spec generation-ready validation |
398|398|| `--skip-dataset-eval` | `bool` | `False` | Skip DeepEval dataset quality gate |
399|399|| `--allow-metadata-repair` | `bool` | `False` | Dev/template-only escape hatch: omit `--require-complete-metadata` so sanitizer can repair missing metadata during smoke runs |
400|400|| `--dataset-eval-mode` | `str` | `fast` | `fast`, `release` |
401|401|| `--dataset-eval-cases-per-category N` | `int` | *mode-dep.* | Rows sampled per category for pipeline dataset-eval |
402|402|| `--num-eval-questions N` | `int` | `5` | Number of evaluation questions |
403|403|
404|404|---
405|405|
406|406|### `plan-execution`
407|407|Recommend local vs remote (Colab) for generation/training.
408|408|
409|409|| Flag | Type | Default | Description |
410|410||------|------|---------|-------------|
411|411|| `--spec PATH` | `str` | *required* | Path to subject spec JSON |
412|412|| `--preset PRESET` | `str` | — | Training preset |
413|413|| `--local-vram-gb GB` | `float` | *auto-detected* | Override detected local VRAM |
414|414|| `--json` | `bool` | `False` | Output JSON |
415|415|
416|416|---
417|417|
418|418|### `plan-batch`
419|419|Batch plan local vs remote queues and generate Colab notebooks.
420|420|
421|421|| Flag | Type | Default | Description |
422|422||------|------|---------|-------------|
423|423|| `--spec-glob GLOB` | `str` | `data/npcs/specs/*.json` | Spec glob under project root |
424|424|| `--spec PATH` (repeatable) | `str[]` | — | Explicit spec path (repeatable) |
425|425|| `--presets PRESETS` | `str` | `fast-3b` | Comma-separated presets |
426|426|| `--local-vram-gb GB` | `float` | — | Override detected local VRAM |
427|427|| `--json` | `bool` | `False` | Output JSON |
428|428|| `--write-plan PATH` | `str` | — | Write plan JSON to file |
429|429|| `--generate-colab-notebooks` | `bool` | `False` | Generate notebooks for remote queue |
430|430|| `--colab-output-dir PATH` | `str` | `colab/outputs` | Notebook output directory |
431|431|| `--drive-repo-dir PATH` | `str` | `/content/drive/MyDrive/Unsloth_Core` | Drive path where repo is cloned |
432|432|
433|433|---
434|434|
435|435|### `batch-export`
436|436|Export all NPCs to GGUF without reloading base model between NPCs.
437|437|
438|438|| Flag | Type | Default | Description |
439|439||------|------|---------|-------------|
440|440|| `--npc KEYS` | `str` | *auto-detect* | Comma-separated NPC keys |
441|441|| `--quantization TYPE` | `str` | `q4_k_m` | GGUF quantization |
442|442|| `--model MODEL` | `str` | *auto-detected* | Base model ID |
443|443|| `--skip-f16` | `bool` | `False` | Skip f16 variants |
444|444|
445|445|---
446|446|
447|447|### `tb-reader`
448|448|Read TensorBoard event files as JSON.
449|449|
450|450|| Flag | Type | Default | Description |
451|451||------|------|---------|-------------|
452|452|| `--run-dir PATH` | `str` | *required* | Path to TensorBoard event directory |
453|453|| `--indent N` | `int` | `2` | JSON indent |
454|454|
455|455|---
456|456|
457|457|### `init` / `new-npc`
458|458|Scaffold a new NPC (folders + spec).
459|459|
460|460|| Flag | Type | Default | Description |
461|461||------|------|---------|-------------|
462|462|| `npc_key` (positional) | `str` | *required* | NPC key (snake_case) |
463|463|| `--subject TEXT` | `str` | — | Subject description |
464|464|| `--name TEXT` | `str` | — | NPC display name |
465|465|| `--force` | `bool` | `False` | Overwrite existing spec |
466|466|| `--skip-spec` | `bool` | `False` | Only create folders, skip spec file |
467|467|
468|468|---
469|469|
470|470|### `audit`
471|471|Health check and context audit.
472|472|
473|473|| Subcommand | Description | Flags |
474|474||-----------|-------------|-------|
475|475|| `audit check` | Quick environment health check | `--full` (bool: full audit) |
476|476|| `audit diagnose` | Diagnose NPC issue | `--npc KEY` (required) |
477|477|| `audit resume` | Recover session context (full audit) | — |
478|478|
479|479|---
480|480|
481|481|### `supabase-check`
482|482|Verify NPC profile + dialogue memory path in Supabase.
483|483|
484|484|| Flag | Type | Default | Description |
485|485||------|------|---------|-------------|
486|486|| `--npc-key KEY` | `str` | *required* | NPC key |
487|487|| `--player-id UUID` | `str` | — | Probe player UUID |
488|488|| `--skip-probe` | `bool` | `False` | Only profile alignment, skip dialogue probe |
489|489|
490|490|---
491|491|
492|492|### `pipeline` (Legacy / Subcommands not listed above)
493|493|
494|494|---
495|495|
496|496|## 2. Dataset Categories & Contract Constants
497|497|
498|498|Defined in `src/core/dataset/dataset_contracts.py`.
499|499|
500|500|### 5 Supported Categories
501|501|
502|502|| Category | Description | Min Examples (SFT) | Role |
503|503||----------|-------------|-------------------:|------|
504|504|| `identity` | Persona introduction and self-identification | **8** | Defines NPC character, personality, background |
505|505|| `teaching` | Subject-matter explanations | **32** | Core knowledge transfer (largest category) |
506|506|| `dialogue` | Natural conversation handling | **16** | Clarification, deep-dives, follow-ups |
507|507|| `quest` | Scenario-based interactions | **8** | Challenges, practice problems, quizzes |
508|508|| `refusal` | Safe boundary responses | **8** | Polite refusal, scope-limiting, safety guardrails |
509|509|| **Total** | | **72** | |
510|510|
511|511|### 3 Difficulty Levels
512|512|
513|513|| Level | Used for |
514|514||-------|----------|
515|515|| `beginner` | Simple explanations, foundational concepts |
516|516|| `intermediate` | Deeper analysis, comparative questions |
517|517|| `advanced` | Expert-level nuance, edge cases, synthesis |
518|518|
519|519|### Contract Helpers
520|520|
521|521|| Function | Purpose |
522|522||----------|---------|
523|523|| `expected_examples_per_category(spec)` | Returns target counts from spec or minimum contract |
524|524|| `generation_request_counts_for_training_targets(targets, val_split, include_validation)` | Inflates generation counts to account for validation holdout |
525|525|| `summarize_jsonl_dataset(path)` | Returns category/difficulty/concept distribution, content hash |
526|526|| `calculate_distribution_gaps(expected, observed)` | Returns underfilled categories with shortfall counts |
527|527|| `dataset_contract_from_spec(spec)` | Builds machine-readable contract block: categories, minimums, difficulties |
528|528|| `file_sha256(path)` | Returns `sha256:{hex}` content hash |
529|529|| `record_pipeline_stage()` | One-shot helper to record a pipeline stage to `.pipeline/run_manifest.json` |
530|530|
531|531|---
532|532|
533|533|## 3. Generation Techniques
534|534|
535|535|| Technique | Description | Backend |
536|536||-----------|-------------|---------|
537|537|| `template` | Fast deterministic generation from curated prompt templates | Built-in Jinja-like templates (`generation_profiles.py`) |
538|538|| `docs` | Grounded generation from curated reference-doc manifests | Reference docs in `data/npcs/reference_docs/` |
539|539|| `ollama` | LLM-driven synthetic data via local Ollama | Ollama API (`http://localhost:11434`) |
540|540|| `openai` | LLM-driven synthetic data via OpenAI API | OpenAI chat completions |
541|541|| `anthropic` | LLM-driven synthetic data via Anthropic API | Anthropic messages API |
542|542|
543|543|### Category Templates (from `generation_profiles.py`)
544|544|
545|545|| Category | User Template Count | Assistant Generator |
546|546||----------|:-------------------:|---------------------|
547|547|| `identity` | 8 | `generate_identity_response(spec)` |
548|548|| `teaching` | 32 | `generate_teaching_response(spec, concept_a, concept_b, difficulty, retriever)` |
549|549|| `dialogue` | 16 | `generate_dialogue_response(spec, concept, dialogue_type, retriever)` |
550|550|| `quest` | 8 | `generate_quest_response(spec, concept, scenario_name, retriever)` |
551|551|| `refusal` | 8 | `generate_refusal_response(spec, boundary)` |
552|552|
553|553|### DialogueGuardrail Parameters
554|554|
555|555|| Parameter | Default | Description |
556|556||-----------|---------|-------------|
557|557|| `max_sentences` | `5` | Max sentences in NPC response |
558|558|| `max_characters` | `500` | Max characters in NPC response |
559|559|| `allow_formatting` | `True` | Allow markdown bolding, headers, lists |
560|560|
561|561|### Refusal Boundary Types
562|562|
563|563|| Boundary Pattern | Handler |
564|564||-----------------|---------|
565|565|| `speculate` / `counterfactual` | Labels as speculation, redirects to documented facts |
566|566|| `misinformation` / `conspiracy` | Declines, redirects to evidence-based sources |
567|567|| `unsupported_certainty` / `date range` | Gives ranges, declines false precision |
568|568|| `medical` / `dietary` | Declines, redirects to safe cooking/exercise basics |
569|569|| `unsafe` / `food preparation` | Declines unsafe methods, offers safe alternatives |
570|570|| `aliens` / `extraterrestrial` | Declines, redirects to astronomy facts |
571|571|| `topic change` / `different topic` | Allows topic switch within subject scope |
572|572|
573|573|---
574|574|
575|575|## 4. Ollama Model Presets
576|576|
577|577|Defined in `etc/ollama/model-presets.yaml`, resolved by `src/core/ops/ollama_model_presets.py`.
578|578|
579|579|### Generation Presets
580|580|
581|581|| Preset Name | Resolved Model | Params | Use Case |
582|582||-------------|---------------|:------:|----------|
583|583|| `generate-qwen25` | `qwen2.5:7b` | 7B | **Default generation** (balanced speed/quality) |
584|584|| `generate-llama31` | `llama3.1:8b` | 8B | Alternative generation model |
585|585|| `generate-qwen35-exp` | `qwen3.5:latest` | ~8B | Experimental — latest Qwen 3.5 |
586|586|| `generate-qwen3-exp` | `qwen3:latest` | 8.2B | Qwen 3 (also used as judge) |
587|587|
588|588|### Judge Presets
589|589|
590|590|| Preset Name | Resolved Model | Params | Use Case |
591|591||-------------|---------------|:------:|----------|
592|592|| `judge-qwen25` | `qwen2.5:7b` | 7B | Alternative judge |
593|593|| `judge-llama31-exp` | `llama3.1:8b` | 8B | Experimental judge |
594|594|| `judge-qwen35-exp` | `qwen3.5:latest` | ~8B | Experimental — latest Qwen 3.5 |
595|595|| `judge-qwen3-exp` | `qwen3:latest` | 8.2B | Experimental — Qwen 3 |
596|596|
597|597|### Defaults & Resolution
598|598|
599|599|| Constant | Value |
600|600||----------|-------|
601|601|| Default generation preset | `generate-qwen25` → `qwen2.5:7b` |
602|602|| Default judge preset | `judge-qwen25` → `qwen2.5:7b` |
603|603|| Safety fallback (judge) | `qwen2.5:7b` |
604|604|| Safety fallback (generation) | `qwen2.5:7b` |
605|605|
606|606|**Resolution priority** (`resolve_ollama_model()`):
607|607|1. Explicit CLI `--model` (wins unconditionally)
608|608|2. Explicit CLI `--preset` (maps through YAML)
609|609|3. Role-specific default preset (`default_generation` / `default_judge`)
610|610|4. Safety fallback model
611|611|
612|612|### Ollama Serving Configuration
613|613|
614|614|| Env Variable | Value | Effect |
615|615||-------------|-------|--------|
616|616|| `OLLAMA_NUM_PARALLEL` | `4` | 4 concurrent request slots |
617|617|| `OLLAMA_FLASH_ATTENTION` | `1` | Enables flash attention |
618|618|| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | 8-bit KV cache |
619|619|
620|620|---
621|621|
622|622|## 5. Training Presets
623|623|
624|624|Defined in `etc/presets/*.yaml`. Merged on top of `etc/lora-sft-base.yaml`.
625|625|
626|626|### Preset Comparison Table
627|627|
628|628|| Parameter | Base YAML | `smoke` | `fast-3b` | `fast-1.7b` | `safe-any` | `premium-3b` | `remote-3b-quality` |
629|629||-----------|:---------:|:-------:|:---------:|:-----------:|:----------:|:------------:|:-------------------:|
630|630|| **Target GPU** | 6GB | any | 6GB | 6GB | any | 15GB+ (T4/L4) | Colab |
631|631|| **Model** | Llama-3.2-3B | *inherits* | *inherits* | *inherits* | *inherits* | *inherits* | **Llama-3.2-3B** (explicit) |
632|632|| **max_steps** | — | **10** | — | — | — | — | — |
633|633|| **num_epochs** | 3 | **1** | 3 | 3 | 3 | 3 | **5** |
634|634|| **batch_size** | 1 | **1** | **1** | **1** | **1** | **4** | **4** |
635|635|| **gradient_accumulation_steps** | 8 | **2** | **8** | **4** | **8** | **4** | **4** |
636|636|| **effective batch size** | 8 | 2 | 8 | 4 | 8 | 16 | 16 |
637|637|| **max_seq_length** | 2048 | **512** | 2048 | **1024** | **1024** | 2048 | **2048** |
638|638|| **learning_rate** | 0.0002 | 0.0002 | 0.0002 | 0.0002 | 0.0002 | **0.0002** | **0.00015** |
639|639|| **warmup_steps** | 10 | — | 10 | **10** | **5** | **20** | **30** |
640|640|| **save_steps** | 50 | **5** | 50 | 50 | 50 | 50 | **25** |
641|641|| **eval_steps** | 50 | **5** | 50 | 50 | 50 | 50 | **25** |
642|642|| **weight_decay** | 0.01 | 0.01 | 0.01 | 0.01 | 0.01 | 0.01 | **0.01** |
643|643|| **packing** | true | true | true | true | true | true | **true** |
644|644|| **train_on_responses_only** | true | true | true | true | true | true | **true** |
645|645|| **lr_scheduler_type** | linear | linear | linear | linear | linear | linear | **cosine** |
646|646|| **LoRA r** | 16 | **8** | **16** | **16** | **8** | **32** | **64** |
647|647|| **LoRA alpha** | 32 | **16** | **32** | **32** | **16** | **64** | **128** |
648|648|| **LoRA dropout** | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | **0.05** | **0.05** |
649|649|| **target_modules** | full set | *inherits* | *inherits* | *inherits* | *inherits* | *inherits* | **full set** (explicit) |
650|650|| **W&B enabled** | false | false | false | false | false | false | **true** |
651|651|
652|652|### Preset Selection Heuristic
653|653|
654|654|| Condition | Chosen Preset |
655|655||-----------|---------------|
656|656|| Debug/testing | `smoke` |
657|657|| 3B model, VRAM ≥ 10GB | `fast-3b` |
658|658|| 1.5B–1.7B model, VRAM ≥ 6GB | `fast-1.7b` |
659|659|| Any size, limited VRAM (or auto-fallback) | `safe-any` |
660|660|| 15GB+ VRAM (T4/L4 Colab) | `premium-3b` |
661|661|| Remote execution, maximum quality | `remote-3b-quality` |
662|662|
663|663|### LoRA Target Modules (default)
664|664|
665|665|```
666|666|q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj
667|667|```
668|668|
669|669|### W&B Preset (`wandb.yaml`)
670|670|
671|671|| Key | Value |
672|672||-----|-------|
673|673|| `wandb.enabled` | `true` |
674|674|
675|675|Simple override that flips W&B on for any base config.
676|676|
677|677|---
678|678|
679|679|## 6. Training Parameters (from base YAML)
680|680|
681|681|Defined in `etc/lora-sft-base.yaml` — the full schema merged with presets at runtime.
682|682|
683|683|### Model Section
684|684|
685|685|| Key | Default | Description |
686|686||-----|---------|-------------|
687|687|| `model` | `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` | Base HuggingFace model ID |
688|688|
689|689|### Data Section
690|690|
691|691|| Key | Default | Description |
692|692||-----|---------|-------------|
693|693|| `data.format_type` | `chatml` | ChatML format for training data |
694|694|
695|695|### Training Section
696|696|
697|697|| Key | Default | Description |
698|698||-----|---------|-------------|
699|699|| `training.training_type` | `lora` | Training type (only LoRA supported) |
700|700|| `training.max_seq_length` | `2048` | Max sequence length (tokens) |
701|701|| `training.load_in_4bit` | `true` | 4-bit quantization (QLoRA) |
702|702|| `training.num_epochs` | `3` | Number of training epochs |
703|703|| `training.learning_rate` | `0.0002` | AdamW learning rate |
704|704|| `training.batch_size` | `1` | Per-device batch size |
705|705|| `training.gradient_accumulation_steps` | `8` | Gradient accumulation steps |
706|706|| `training.warmup_steps` | `10` | Linear warmup steps |
707|707|| `training.save_steps` | `50` | Checkpoint save interval |
708|708|| `training.eval_steps` | `50` | Evaluation interval |
709|709|| `training.weight_decay` | `0.01` | AdamW weight decay |
710|710|| `training.packing` | `true` | Pack multiple sequences into one |
711|711|| `training.train_on_responses_only` | `true` | Mask loss on user turns |
712|712|
713|713|### Additional Runtime Training Parameters
714|714|
715|715|| Parameter | Location | Effect |
716|716||-----------|----------|--------|
717|717|| `training.max_steps` | Presets | Override epochs with max step count (`smoke`: 10) |
718|718|| `training.lr_scheduler_type` | Presets | Scheduler type (`cosine` in `remote-3b-quality`) |
719|719|
720|720|### LoRA Section
721|721|
722|722|| Key | Default | Description |
723|723||-----|---------|-------------|
724|724|| `lora.r` | `16` | LoRA rank |
725|725|| `lora.alpha` | `32` | LoRA alpha scaling |
726|726|| `lora.dropout` | `0.0` | LoRA dropout rate |
727|727|| `lora.target_modules` | `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj` | Comma-separated target module list |
728|728|
729|729|### Logging Section
730|730|
731|731|| Key | Default | Description |
732|732||-----|---------|-------------|
733|733|| `logging.enable_tensorboard` | `true` | Enable TensorBoard logging |
734|734|
735|735|---
736|736|
737|737|## 7. Sanitize Settings
738|738|
739|739|Parameters applied by `src/core/dataset/sanitize_dataset.py` (invoked via `ucore sanitize`).
740|740|
741|741|### Structural Validation
742|742|
743|743|| Setting | Default | Description |
744|744||---------|---------|-------------|
745|745|| `--min-length` | `10` | Min chars for assistant response |
746|746|| `--max-sentences` | `5` | Max sentences for assistant response |
747|747|| `--strict-mode` | `False` | Raise on structural errors vs discard |
748|748|| `--artifact-check` | `strict` | AI artifact handling: `strict`, `warn`, `off` |
749|749|| `--verbose-artifacts` | `False` | Show exact artifact pattern matched |
750|750|
751|751|### AI Artifact Patterns (checked in responses)
752|752|
753|753|| Pattern | Example |
754|754||---------|---------|
755|755|| AI disclaimers | `"as an ai"`, `"as a language model"`, `"i don't have personal feelings"` |
756|756|| Vendor mentions | `"openai"`, `"anthropic"` |
757|757|| Meta-references | `"knowledge cutoff"`, `"from my training data"`, `"i'm just an ai"` |
758|758|
759|759|### Quality Scoring
760|760|
761|761|| Setting | Default | Description |
762|762||---------|---------|-------------|
763|763|| `--quality-threshold-pass` | `70` | Minimum total score to pass |
764|764|| `--quality-threshold-flag` | `50` | Below this, examples flagged for review |
765|765|| `--discard-below-score` | `0` | Discard examples below this score (0 = keep all) |
766|766|| `--quality-report` | `False` | Print quality score distribution |
767|767|
768|768|### Metadata Handling
769|769|
770|770|| Setting | Default | Description |
771|771||---------|---------|-------------|
772|772|| `--no-fix-metadata` | `False` | Disable auto-repair of missing metadata fields |
773|773|| `--require-complete-metadata` | `False` | Error out if any metadata field missing |
774|774|| `--write-manifest` / `--no-write-manifest` | `True` | Enable/disable enriched manifest writing |
775|775|| `--manifest-path PATH` | — | Override manifest output path |
776|776|
777|777|### Deduplication
778|778|
779|779|| Setting | Default | Description |
780|780||---------|---------|-------------|
781|781|| `--dedup` / `--no-dedup` | `True` | Enable/disable content_hash deduplication |
782|782|| `--dedup-report` | `False` | Show which content hashes removed |
783|783|
784|784|### Output & Debug
785|785|
786|786|| Setting | Default | Description |
787|787||---------|---------|-------------|
788|788|| `--output`, `-o` | `*_clean.jsonl` | Output JSONL path |
789|789|| `--verbose`, `-v` | `False` | Print discarded examples and metadata warnings |
790|790|| `--spec PATH` | — | NPC spec JSON for better quality scoring |
791|791|| `--strict-canonical` | `False` | Require canonical dataset path |
792|792|| `--debug` | `False` | Re-raise exceptions with traceback |
793|793|
794|794|---
795|795|
796|796|## 8. Dataset Eval (DeepEval) Settings
797|797|
798|798|Parameters for `src/core/dataset/dataset_eval.py` (invoked via `ucore dataset-eval`).
799|799|
800|800|### Mode-Dependent Defaults
801|801|
802|802|| Parameter | `fast` mode | `release` mode |
803|803||-----------|:-----------:|:--------------:|
804|804|| `--cases-per-category` | 1 | 5 |
805|805|| Blocking on metric failure | No (diagnostics only) | Yes |
806|806|| Use case | Iteration-friendly | Strict final checks |
807|807|
808|808|### All Parameters
809|809|
810|810|| Parameter | Type | Default | Description |
811|811||-----------|------|---------|-------------|
812|812|| `--mode` | `str` | `fast` | `fast`, `release` |
813|813|| `--judge-model MODEL` | `str` | *resolved from presets* | Local Ollama judge model |
814|814|| `--judge-preset PRESET` | `str` | *resolved from presets* | Named Ollama judge preset |
815|815|| `--ollama-base-url URL` | `str` | `http://localhost:11434` | Ollama server URL |
816|816|| `--judge-temperature T` | `float` | `0.0` | Judge temperature |
817|817|| `--cases-per-category N` | `int` | *mode-dep.* | Rows sampled per category |
818|818|| `--categories CATS` | `str` | — | Comma-separated category filter |
819|819|| `--identifier ID` | `str` | — | DeepEval run identifier |
820|820|| `--display` | `str` | `all` | `all`, `failing`, `passing` |
821|821|| `--ignore-errors` | `bool` | `False` | Continue when individual metric calls error |
822|822|| `--soft-fail` | `bool` | `False` | Write artifacts but return 0 even on failures |
823|823|| `--output PATH` | `str` | — | Quality summary JSON path |
824|824|| `--technique TECH` | `str` | `template` | Dataset technique to evaluate |
825|825|| `--confident` | `bool` | `False` | Enforce that CONFIDENT_API_KEY is configured (exits with error if missing) |
826|826|
827|827|### Quality Gate Checks (in `train.py`)
828|828|
829|829|| Check | Blocks Training |
830|830||-------|:---------------:|
831|831|| Dataset is `train_clean.jsonl` (not raw `train.jsonl`) | Yes |
832|832|| `quality_summary.json` exists with `status: "ok"` | Yes |
833|833|| Zero distribution gaps | Yes |
834|834|| Zero unknown rows | Yes |
835|835|| Clean sanitizer quality signals | Yes |
836|836|| Matching dataset content hash | Yes |
837|837|| Failing sampled DeepEval cases (`release` mode) | Yes |
838|838|| Failing sampled DeepEval cases (`fast` mode) | **No** (diagnostics only) |
839|839|
840|840|### Opt-Out
841|841|
842|842|| Flag | Effect |
843|843||------|--------|
844|844|| `--allow-ungated-dataset` | Skip all quality gate checks |
845|845|| `--deepeval-soft-fail` | Run DeepEval but don't fail on metric failures |
846|846|| `--skip-dataset-eval` | Skip running DeepEval entirely |
847|847|
848|848|---
849|849|
850|850|## 9. Evaluation Settings (./ucore evaluate)
851|851|
852|852|Parameters for `src/core/evaluation/evaluate.py`.
853|853|
854|854|### Eval Presets (from `etc/eval-presets.yaml`)
855|855|
856|856|| Preset | Questions | Judge | HTML Report | Description |
857|857||--------|:---------:|:-----:|:-----------:|-------------|
858|858|| `smoke` | 3 | No | No | Fast smoke test |
859|859|| `quick` | 10 | No | No | Quick check |
860|860|| `full` | 25 | Yes | Yes | Full evaluation |
861|861|
862|862|### All Evaluate Flags
863|863|
864|864|| Parameter | Type | Default | Description |
865|865||-----------|------|---------|-------------|
866|866|| `--baseline PATH` | `str` | — | Baseline GGUF model path |
867|867|| `--candidate PATH` | `str` | — | Candidate GGUF model path |
868|868|| `--model`, `-m PATH` | `str` | — | Single model (interactive) |
869|869|| `--spec`, `-s PATH` | `str` | — | Subject spec JSON |
870|870|| `--val-data PATH` | `str` | — | Validation JSONL |
871|871|| `--num-questions N` | `int` | `10` | Number of eval questions |
872|872|| `--output`, `-o PATH` | `str` | — | Output report path |
873|873|| `--report-html` | `bool` | `False` | Generate HTML report (Chart.js) |
874|874|| `--judge` | `bool` | `False` | Use local Ollama judge |
875|875|| `--judge-model MODEL` | `str` | `qwen2.5:7b` | Judge model |
876|876|| `--track` | `bool` | `False` | Track in `eval/results/` |
877|877|| `--interactive`, `-i` | `bool` | `False` | Interactive chat mode |
878|878|| `--training-metrics [PATH]` | `str` | — | Show TensorBoard metrics |
879|879|| `--deepeval` | `bool` | `False` | Run DeepEval model quality evaluation after conventional eval |
880|880|| `--deepeval-judge-model` | `str` | `qwen3:latest` | Ollama model to use as judge |
881|881|| `--deepeval-identifier` | `str` | — | Custom identifier for the DeepEval test run |
882|882|
883|883|### Inference Engine Flags
884|884|
885|885|| Parameter | Type | Default | Description |
886|886||-----------|------|---------|-------------|
887|887|| `--port N` | `int` | `8888` | llama-server port |
888|888|| `--gpu-layers N` | `int` | `99` | GPU layers (0 = CPU-only) |
889|889|| `--max-tokens N` | `int` | `256` | Max generated tokens |
890|890|| `--host ADDR` | `str` | `127.0.0.1` | llama-server host |
891|891|| `--base-model PATH` | `str` | — | Base GGUF for LoRA eval |
892|892|| `--lora-weight T` | `float` | `1.0` | LoRA adapter weight |
893|893|
894|894|### Feedback Integration
895|895|
896|896|| Flag | Description |
897|897||------|-------------|
898|898|| `--feedback-json PATH` | Save structured per-concept eval results for feedback loop |
899|899|| `--npc-key KEY` | NPC key for TensorBoard runs lookup |
900|900|
901|901|---
902|902|
903|903|## 10. Feedback Loop Settings
904|904|
905|905|Parameters for `src/core/training/feedback_loop.py` (invoked via `ucore feedback`).
906|906|
907|907|### Thresholds
908|908|
909|909|| Parameter | Default | Description |
910|910||-----------|---------|-------------|
911|911|| `--win-rate-threshold` | `0.5` | Min win rate vs baseline |
912|912|| `--quality-threshold` | `25.0` | Max quality score (lower = better) |
913|913|| `--violation-threshold` | `1` | Max constraint violations |
914|914|
915|915|### Execution Control
916|916|
917|917|| Parameter | Default | Description |
918|918||-----------|---------|-------------|
919|919|| `--dry-run` | `False` | Analyze without regenerating |
920|920|| `--auto`, `-y` | `False` | Auto-accept all suggestions |
921|921|| `--skip-gap-detection` | `False` | Skip knowledge coverage check |
922|922|| `--save-gaps PATH` | — | Save knowledge gap report to JSON |
923|923|| `--json` | `False` | Machine-readable JSON summary |
924|924|| `--auto-retrain` | `False` | After regeneration, auto-retrain and re-evaluate |
925|925|| `--train-preset` | `fast-3b` | Training preset for auto-retrain |
926|926|| `--baseline PATH` | — | Baseline GGUF for auto-evaluation |
927|927|
928|928|### Regeneration Parameters
929|929|
930|930|| Parameter | Default | Description |
931|931||-----------|---------|-------------|
932|932|| `--regeneration-technique` | `template` | `template`, `ollama` |
933|933|| `--regeneration-preset` | `generate-qwen25` | Ollama generation preset |
934|934|| `--regeneration-model` | `qwen2.5:7b` | Exact Ollama regeneration model |
935|935|| `--regeneration-url` | `http://localhost:11434` | Ollama base URL for regeneration |
936|936|| `--regeneration-batch-size` | `4` | Ollama batch size |
937|937|
938|938|### DeepEval Parameters (Post-Regeneration)
939|939|
940|940|| Parameter | Default | Description |
941|941||-----------|---------|-------------|
942|942|| `--deepeval-judge-preset` | *resolved* | Named Ollama judge preset |
943|943|| `--deepeval-judge-model` | — | Exact Ollama judge model |
944|944|| `--deepeval-ollama-url` | `http://localhost:11434` | Ollama base URL for DeepEval |
945|945|| `--deepeval-cases-per-category` | `1` | Cases per category for fast DeepEval |
946|946|| `--deepeval-soft-fail` | `False` | Don't abort dataset evaluation on metric failure |
947|947|
948|948|### Knowledge Gap Detection
949|949|
950|950|| Gap Type | Cause | Fix |
951|951||----------|-------|-----|
952|952|| `training_density` | Not enough training examples | Regenerate with `--concept-focus` |
953|953|| `knowledge_gap` | Missing reference material | Add reference docs + re-index |
954|954|
955|955|---
956|956|
957|957|## 11. Preflight / Preheat Settings
958|958|
959|959|Parameters for `src/core/ops/preflight.py`.
960|960|
961|961|### CLI Flags
962|962|
963|963|| Flag | Type | Default | Description |
964|964||------|------|---------|-------------|
965|965|| `--phase` | `str` | `train` | `train`, `dataset_eval`, `export` |
966|966|| `--preset PRESET` | `str` | — | Requested training preset |
967|967|| `--spec PATH` | `str` | — | Subject spec JSON path |
968|968|| `--technique TECH` | `str` | — | Dataset technique name |
969|969|| `--ollama-url URL` | `str` | `http://localhost:11434` | Ollama server URL |
970|970|| `--no-auto-unload-ollama` | `bool` | `False` | Do not stop running Ollama models |
971|971|| `--no-gcc-check` | `bool` | `False` | Skip gcc validation even for training |
972|972|| `--json` | `bool` | `False` | Print JSON only |
973|973|
974|974|### Checks Performed
975|975|
976|976|| Check | Description | Phase Required |
977|977||-------|-------------|:-------------:|
978|978|| GPU memory inventory | `nvidia-smi` free/total VRAM in GiB | All |
979|979|| Auto-downgrade VRAM | `fast-3b` → `safe-any` when total VRAM < 10GB | `train` |
980|980|| Ollama auto-unload | Detect + stop running Ollama models | `train`, `dataset_eval` |
981|981|| GCC toolchain | Verify `gcc` in PATH (Triton requirement) | `train` |
982|982|
983|983|### PreflightReport Fields
984|984|
985|985|| Field | Type | Description |
986|986||-------|------|-------------|
987|987|| `status` | `str` | `"ok"`, `"degraded"`, `"blocked"` |
988|988|| `phase` | `str` | Pipeline phase |
989|989|| `preset_requested` | `str` | What was asked for |
990|990|| `preset_effective` | `str` | What will actually run |
991|991|| `technique` | `str` | Dataset technique |
992|992|| `total_vram_gb` | `float` | Total GPU VRAM (GiB) |
993|993|| `free_vram_gb` | `float` | Free GPU VRAM (GiB) |
994|994|| `gcc_ok` | `bool` | GCC available |
995|995|| `gcc_path` | `str` | GCC binary path |
996|996|| `running_ollama_models` | `list[str]` | Models detected running |
997|997|| `stopped_ollama_models` | `list[str]` | Models auto-stopped |
998|998|| `recommendation.training.location` | `str` | `"local"` or `"remote_colab"` |
999|999|| `recommendation.training.reason` | `str` | Why that location was chosen |
1000|1000|| `warnings` | `list[str]` | Non-blocking issues |
1001|1001|| `errors` | `list[str]` | Blocking issues |
1002|1002|
1003|1003|---
1004|1004|
1005|1005|## 12. Model Size → Preset Mapping
1006|1006|
1007|1007|Defined in `etc/model-presets.yaml`.
1008|1008|
1009|1009|### Exact Model Mappings
1010|1010|
1011|1011|| Model ID | Preset |
1012|1012||----------|--------|
1013|1013|| `unsloth/Llama-3.2-3B-Instruct-bnb-4bit` | `fast-3b` |
1014|1014|| `unsloth/Llama-3.2-1B-Instruct-bnb-4bit` | `safe-any` |
1015|1015|| `unsloth/Qwen3-1.7B-unsloth-bnb-4bit` | `fast-1.7b` |
1016|1016|| `unsloth/Llama-3.1-8B-Instruct-bnb-4bit` | `premium-3b` |
1017|1017|
1018|1018|### Size Bucket Mappings
1019|1019|
1020|1020|| Model Size Bucket | Preset | Typical VRAM (4-bit LoRA) |
1021|1021||:-----------------:|--------|:-------------------------:|
1022|1022|| `0.5b` | `safe-any` | 2.0 GB |
1023|1023|| `1b` | `safe-any` | 2.5 GB |
1024|1024|| `1.7b` | `fast-1.7b` | 3.5 GB |
1025|1025|| `3b` | `fast-3b` | 5.0 GB |
1026|1026|| `7b` | `premium-3b` | 12.0 GB |
1027|1027|| `8b` | `premium-3b` | 14.0 GB |
1028|1028|
1029|1029|### Resolution Logic
1030|1030|
1031|1031|1. **Exact model ID** match in `exact_models` → use directly
1032|1032|2. **Size bucket** heuristic → use mapped preset
1033|1033|3. **Default** → `fast-3b`
1034|1034|
1035|1035|---
1036|1036|
1037|1037|## 13. Workload Policy
1038|1038|
1039|1039|Defined in `etc/workload-policy.yaml`.
1040|1040|
1041|1041|### Safety Parameters
1042|1042|
1043|1043|| Key | Value | Description |
1044|1044||-----|:-----:|-------------|
1045|1045|| `safety.training_vram_safety_margin` | `1.25` | Require local VRAM to exceed estimate by this multiplier |
1046|1046|| `local_caps.ollama_min_vram_gb` | `6` | If Ollama generation selected and VRAM < 6GB, prefer remote |
1047|1047|
1048|1048|### Model VRAM Baselines (4-bit LoRA, observed)
1049|1049|
1050|1050|| Size | Baseline VRAM |
1051|1051||:----:|:-------------:|
1052|1052|| 0.5b | 2.0 GB |
1053|1053|| 1b | 2.5 GB |
1054|1054|| 1.7b | 3.5 GB |
1055|1055|| 3b | 5.0 GB |
1056|1056|| 7b | 12.0 GB |
1057|1057|| 8b | 14.0 GB |
1058|1058|
1059|1059|### Policy Notes
1060|1060|
1061|1061|- Baselines reflect observed Unsloth 4-bit LoRA behavior on RTX 3060 6GB workflow
1062|1062|- Use `--preset safe-any` if local run OOMs
1063|1063|- Prefer W&B/PeerLM remote credits for reporting/evaluation (not Colab/Kaggle training)
1064|1064|
1065|1065|---
1066|1066|
1067|1067|## 14. Promotion Rules
1068|1068|
1069|1069|Defined in `etc/promotion-rules.yaml`. A model must pass **ALL** thresholds before being promoted to "best".
1070|1070|
1071|1071|| Threshold | Value | Description |
1072|1072||-----------|:-----:|-------------|
1073|1073|| `max_training_loss` | `2.0` | Max final training loss (Onyx v2 converges ~1.76–1.80) |
1074|1074|| `min_eff_batch_size` | `4` | Minimum effective batch size |
1075|1075|| `min_train_examples` | `10` | Minimum number of training examples |
1076|1076|
1077|1077|These prevent garbage models from being promoted due to NaN loss or bad config.
1078|1078|
1079|1079|---
1080|1080|
1081|1081|## 15. Export Settings
1082|1082|
1083|1083|### Adapter Export (Default, for LLMUnity)
1084|1084|
1085|1085|| Parameter | Default | Description |
1086|1086||-----------|---------|-------------|
1087|1087|| `--outtype` | `f16` | Output format: `f32`, `f16`, `bf16`, `q8_0` |
1088|1088|| Script | `convert_lora_to_gguf.py` | Prebuilt in `~/.unsloth/llama.cpp/` |
1089|1089|| Output size | ~MBs | Lightweight LoRA weights only |
1090|1090|| Unity usage | `--lora` flag on `llama-server` | No base model needed in export |
1091|1091|
1092|1092|### Full-Merge Export (Standalone GGUF)
1093|1093|
1094|1094|| Parameter | Default | Description |
1095|1095||-----------|---------|-------------|
1096|1096|| `--full-merge` | `False` | Produce standalone merged GGUF |
1097|1097|| `--quantization` | `q4_k_m` | GGUF quantization type |
1098|1098|| `--skip-f16` | `False` | Skip f16 variant in full-merge mode |
1099|1099|| `--maximum-memory GB` | — | Max memory for `save_pretrained_gguf` |
1100|1100|| Quantization binary | `llama-quantize` | Prebuilt in `~/.unsloth/llama.cpp/` |
1101|1101|
1102|1102|### Output File Naming
1103|1103|
1104|1104|| Mode | Pattern |
1105|1105||------|---------|
1106|1106|| Adapter | `{npc_key}-lora-f16.gguf` |
1107|1107|| Full-merge | `{npc_key}-{model_short}-{quant}.gguf` |
1108|1108|
1109|1109|### Batch Export (`ucore batch-export`)
1110|1110|
1111|1111|| Parameter | Default | Description |
1112|1112||-----------|---------|-------------|
1113|1113|| `--npc` | *auto-detect* | Comma-separated NPC keys |
1114|1114|| `--quantization` | `q4_k_m` | GGUF quantization |
1115|1115|| `--model` | *auto-detected* | Base model ID |
1116|1116|| `--skip-f16` | `False` | Skip f16 variants |
1117|1117|
1118|1118|### Deploy to Unity (`ucore deploy`)
1119|1119|
1120|1120|| Parameter | Default | Description |
1121|1121||-----------|---------|-------------|
1122|1122|| `--unity-project` | *auto-detected* | Path to Unity project |
1123|1123|| `--dry-run` | `False` | Show what would be done without copying |
1124|1124|| `--skip-export` | `False` | Skip GGUF export step |
1125|1125|| `--export-only` | `False` | Only export, skip Unity copy |
1126|1126|
1127|1127|---
1128|1128|
1129|1129|## 16. Engine / Inference Settings
1130|1130|
1131|1131|### llama-server (used by evaluate.py)
1132|1132|
1133|1133|| Parameter | Default | Description |
1134|1134||-----------|---------|-------------|
1135|1135|| `--port` | `8888` | Server listening port |
1136|1136|| `--gpu-layers` | `99` | GPU layers to offload (0 = CPU-only) |
1137|1137|| `--host` | `127.0.0.1` | Bind address |
1138|1138|| `--lora` | *(adapter path)* | Load LoRA adapter GGUF |
1139|1139|| `--lora-weight` | `1.0` | LoRA adapter weight |
1140|1140|
1141|1141|### Location
1142|1142|
1143|1143|| Binary | Path |
1144|1144||--------|------|
1145|1145|| `llama-server` | `~/.unsloth/llama.cpp/llama-server` |
1146|1146|| `llama-quantize` | `~/.unsloth/llama.cpp/llama-quantize` |
1147|1147|| `convert_lora_to_gguf.py` | `~/.unsloth/llama.cpp/convert_lora_to_gguf.py` |
1148|1148|
1149|1149|---
1150|1150|
1151|1151|## 17. W&B Settings
1152|1152|
1153|1153|### Global Config (from `lora-sft-base.yaml`)
1154|1154|
1155|1155|| Key | Default | Description |
1156|1156||-----|---------|-------------|
1157|1157|| `wandb.enabled` | `false` | Master switch |
1158|1158|| `wandb.project` | `unsloth-core` | W&B project name |
1159|1159|| `wandb.entity` | `andreabenathar-twl-games` | W&B entity/username |
1160|1160|| `wandb.tags` | `[]` | Tags attached to runs |
1161|1161|
1162|1162|### CLI Override Flags
1163|1163|
1164|1164|| Flag | Description |
1165|1165||------|-------------|
1166|1166|| `--wandb` | Enable W&B (overrides config `false`) |
1167|1167|| `--no-wandb` | Disable W&B (overrides config `true`) |
1168|1168|| `--wandb-project NAME` | Override W&B project |
1169|1169|| `--wandb-entity ENTITY` | Override W&B entity |
1170|1170|
1171|1171|### Pipeline Auto-Group
1172|1172|
1173|1173|```python
1174|1174|WANDB_GROUP = f"pipeline-{npc_key}-{timestamp}"
1175|1175|```
1176|1176|
1177|1177|Set as `WANDB_GROUP` and `WANDB_RUN_GROUP` env vars when `--wandb` is passed to `ucore pipeline`.
1178|1178|
1179|1179|### W&B Artifacts Logged
1180|1180|
1181|1181|| Artifact Type | Content | Versioned By |
1182|1182||---------------|---------|-------------|
1183|1183|| Dataset artifact | Dataset JSONL | Content hash, technique, row count |
1184|1184|| LoRA artifact | Final adapter weights | `lora-{npc_key}` |
1185|1185|| GGUF artifact | Exported GGUF | `gguf-{npc_key}` |
1186|1186|| Config snapshot | Frozen training config | Run file |
1187|1187|
1188|1188|---
1189|1189|
1190|1190|## 18. CLI Global Flags
1191|1191|
1192|1192|| Flag | Scope | Env Var | Description |
1193|1193||------|-------|---------|-------------|
1194|1194|| `--workflow-hooks PATH` | All commands | `WORKFLOW_HOOKS_PATH` | Path to JSONL hook log for step tracing |
1195|1195|| `--watch` | All commands | `UCORE_WATCH=1` | Stream with early error alerts + watch log |
1196|1196|| `--watch` (auto-detected) | All commands | `UCORE_WATCH_DIR` | Watch log directory (default: system tempdir) |
1197|1197|
1198|1198|### Early Alert Patterns (built into `--watch` mode)
1199|1199|
1200|1200|| Pattern | Matches |
1201|1201||---------|---------|
1202|1202|| `Traceback (most recent call last):` | Python tracebacks |
1203|1203|| `AssertionError`, `ModuleNotFoundError`, `RuntimeError`, `ValueError`, `KeyError`, `IndexError`, `CalledProcessError`, `OSError` | Common Python errors |
1204|1204|| `ERROR`, `Error:`, `FAILED`, `FAILURE` | General error indicators |
1205|1205|| `Command timed out`, `timed out after` | Timeout events |
1206|1206|| `^\s*F\s+🎯 Evaluating test case` | DeepEval test failures |
1207|1207|
1208|1208|---
1209|1209|
1210|1210|## 19. Spec Validation Checks
1211|1211|
1212|1212|Performed by `src/core/dataset/validate_subject_spec.py` (invoked via `ucore validate-spec`).
1213|1213|
1214|1214|### Generation-Readiness Check (`--generation-ready`)
1215|1215|
1216|1216|| Check | Fail Condition |
1217|1217||-------|----------------|
1218|1218|| JSON parseable | Invalid JSON |
1219|1219|| `npc_key` present | Missing key |
1220|1220|| `reference_doc` path valid | File not found or unreadable |
1221|1221|| Reference doc meets contract | Missing H1, < 5 H2 sections, < 20 bullets, < 250 words, missing safety/refusal/boundary/misconception notes |
1222|1222|| All 5 categories have positive counts | Any category has 0 or negative count |
1223|1223|| All categories meet minimum SFT counts | Any category below `MIN_DATASET_EXAMPLES_PER_CATEGORY` |
1224|1224|| Dataset examples_per_category (if present) | Specifies counts below minimums |
1225|1225|
1226|1226|### Individual Flag Checks
1227|1227|
1228|1228|| Flag | Checks |
1229|1229||------|--------|
1230|1230|| `--require-reference-docs` | `reference_doc` exists and is readable |
1231|1231|| `--require-reference-contract` | Reference doc meets generation-readiness minimums |
1232|1232|| `--require-all-categories` | All 5 dataset categories have positive counts |
1233|1233|| `--require-dataset-minimums` | All categories meet minimum SFT counts |
1234|1234|| `--generation-ready` | All of the above combined |
1235|1235|
1236|1236|---
1237|1237|
1238|1238|## 20. Environment Variables
1239|1239|
1240|1240|| Variable | Set By | Used By | Description |
1241|1241||----------|--------|---------|-------------|
1242|1242|| `WORKFLOW_HOOKS_PATH` | `ucore` / CLI | All pipeline scripts | Path to workflow hook JSONL file |
1243|1243|| `UCORE_WATCH` | `--watch` flag | `ucore` | Enable watch mode (`"1"`) |
1244|1244|| `UCORE_WATCH_DIR` | User | `ucore` | Watch log output directory |
1245|1245|| `WANDB_GROUP` | `ucore pipeline` | W&B | Pipeline run group (`pipeline-{key}-{ts}`) |
1246|1246|| `WANDB_RUN_GROUP` | `ucore pipeline` | W&B | Pipeline run group (alias) |
1247|1247|| `WANDB_JOB_TYPE` | `ucore pipeline` | W&B | Job type (`"train"` / `"eval"`) |
1248|1248|| `DEEPEVAL_OLLAMA_MODEL` | `dataset_eval.py` | DeepEval | Judge model for DeepEval |
1249|1249|| `PIPELINE_DB_URL` | User | `PipelineDB` | Direct PostgreSQL connection string |
1250|1250|| `SUPABASE_URL` | User | `PipelineDB` | Supabase REST API URL |
1251|1251|| `SUPABASE_SERVICE_KEY` | User | `PipelineDB` | Supabase service role key |
1252|1252|| `OLLAMA_NUM_PARALLEL` | Systemd | Ollama | Concurrent request slots (4) |
1253|1253|| `OLLAMA_FLASH_ATTENTION` | Systemd | Ollama | Flash attention enable (1) |
1254|1254|| `OLLAMA_KV_CACHE_TYPE` | Systemd | Ollama | KV cache quantization (`q8_0`) |
1255|1255|
1256|1256|---
1257|1257|
1258|1258|## Appendix A: Category Templates (generation_profiles.py) — Detailed Breakdown
1259|1259|
1260|1260|### Identity Templates (8)
1261|1261|
1262|1262|"Who are you?", "What is your name?", "Tell me about yourself.", "What should I call you?", "Are you a teacher?", "Who am I speaking with?", "What do you teach?", "Can you introduce yourself?"
1263|1263|
1264|1264|### Teaching Templates (32)
1265|1265|
1266|1266|`{concept}`-based: explain, tell me about, what is, how does, why is, example, I don't understand, key ideas behind, compare A and B, how is A related to B, difference between A and B, break down, where can I see, how do experts think, what should I know, real-world example, basics, something interesting, how did X come to be, what makes X useful, can you simplify, I'm struggling, common misconceptions, how do I apply, what do I need, describe like I'm five, main components, why does X matter, metaphor, history behind, how does X fit, advanced aspects.
1267|1267|
1268|1268|### Dialogue Templates (16)
1269|1269|
1270|1270|Clarification (re-explain), follow-up (deeper), example request, concept challenge, application question, memory elaboration, counter-argument, hypothetical, step-by-step, next-steps, cross-domain, alternate angle.
1271|1271|
1272|1272|### Quest Templates (8)
1273|1273|
1274|1274|Challenge, test knowledge, practice exercise, apply scenario, practice problem, quiz, real-world problem, difficult question.
1275|1275|
1276|1276|### Refusal Templates (8 base, plus ~30 boundaries)
1277|1277|
1278|1278|Poem request, meaning of life, baking cake, other-subject homework, stock advice, joke, lottery prediction, medical advice + boundary-specific refusals.
1279|1279|
1280|1280|---
1281|1281|
1282|1282|## Appendix B: Pipeline Script File Index
1283|1283|
1284|1284|| ucore Command | Backend Script |
1285|1285||---------------|---------------|
1286|1286|| `generate` | `src/core/dataset/generate_dataset.py` |
1287|1287|| `generate-ollama` | `src/core/dataset/generate_dataset.py` |
1288|1288|| `sanitize` | `src/core/dataset/sanitize_dataset.py` |
1289|1289|| `dataset-eval` | `src/core/dataset/dataset_eval.py` |
1290|1290|| `train` | `src/core/training/train.py` |
1291|1291|| `validate-spec` | `src/core/dataset/validate_subject_spec.py` |
1292|1292|| `validate-config` | `src/core/ops/validate_config.py` |
1293|1293|| `export` | `src/core/export/export.py` |
1294|1294|| `export-resume` | `src/core/export/export_resume.py` |
1295|1295|| `export-adapter` | `src/core/export/export_adapter.py` |
1296|1296|| `batch-export` | `src/core/export/batch_export.py` |
1297|1297|| `deploy` | `src/core/export/deploy_to_unity.py` |
1298|1298|| `evaluate` | `src/core/evaluation/evaluate.py` |
1299|1299|| `quick-eval` | `src/core/evaluation/quick_eval.py` |
1300|1300|| `track` | `src/core/evaluation/track_eval_results.py` |
1301|1301|| `compare-runs` | `src/core/evaluation/compare_runs.py` |
1302|1302|| `tb-reader` | `src/core/evaluation/tb_reader.py` |
1303|1303|| `feedback` | `src/core/training/feedback_loop.py` |
1304|1304|| `smoke` | `src/core/ops/smoke_test.py` |
1305|1305|| `init` / `new-npc` | `src/core/ops/scaffold_npc.py` |
1306|1306|| `audit` | `src/core/ops/audit.py` (inline) |
1307|1307|| `supabase-check` | `src/core/ops/supabase_integration_check.py` |
1308|1308|| `plan-execution` | `src/core/orchestration/plan_execution.py` |
1309|1309|| `plan-batch` | `src/core/orchestration/plan_batch_execution.py` |
1310|1310|| `pipeline` | `ucore` (inline orchestration, calls all above) |
1311|| `generate-local` | `src/core/dataset/generate_dataset.py` |
1312|| `confident-goldens` | `src/core/ops/confident_goldens.py` |
1313|| `confident-classifiers` | `src/core/ops/confident_classifiers.py` |
1314|| `strategy` | `src/core/ops/npc_production_strategy.py` |
1315|| `compare-local-models` | `src/core/evaluation/compare_local_models.py` |
1316|| `compare-canonical-runs` | `src/core/evaluation/compare_canonical_runs.py` |
1317|| `promote` | `src/core/evaluation/promote.py` |
1318|| `target` | `src/core/orchestration/target_orchestrator.py` |
1319|| `judge-cache` | `src/core/evaluation/judge_cache.py` |
1320|| `report` | `src/core/reporting/report_bundle.py` |
1321|| `inference-server` | `src/core/ops/inference_server.py` |
1322|| `history` | `src/core/history/` |
1323|| `registry` | `src/core/registry/` |
1324|| `new-npc-checklist` | `src/core/ops/scaffold_npc.py` |
1325|1311|
1326|1312|---
1327|1313|
1328|1314|> **Last updated**: 2026-06-10
1329|1315|> **Source files consulted**: 22 files across `etc/`, `src/core/`, and root `ucore`
1330|1316|> **Total line count**: ~2,100 lines in source inputs
1331|1317|
1332|1318|---
1333|1319|
1334|1320|## Appendix C: Pipeline Utility Modules
1335|1321|
1336|1322|| Module | Description | Type | Usage |
1337|1323||--------|-------------|------|-------|
1338|1324|| `src/core/ops/env_loader.py` | Auto-sources `.env.local` across all pipeline scripts | Module | Imported |
1339|1325|| `src/core/ops/confident_push.py` | Push/pull datasets and goldens to/from Confident AI | Module | CLI / Library |
1340|1326|| `src/core/ops/pipeline_manifest.py` | Centralized pipeline run manifest tracking | Module | Library / CLI |
1341|1327|