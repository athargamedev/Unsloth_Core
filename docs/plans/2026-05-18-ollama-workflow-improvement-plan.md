# Ollama Workflow Improvement Plan

> For Hermes: Use subagent-driven-development skill if this plan is executed task-by-task.

Goal: turn the local Ollama workflow into a reliable production-quality loop for all four active NPCs: history_guide, chef_assistant, astronomy_guide, and fitness_coach.

Architecture: fix the measurement layer first, then improve dataset quality, then retrain only after the gates prove the dataset and eval harness are trustworthy. The current LoRAs trained and exported successfully, but the available persisted eval artifacts do not fully match the just-run May 18 workflow, so the first action is to reproduce and persist apples-to-apples evaluation.

Tech Stack: Unsloth_Core ucore CLI, Ollama qwen2.5:7b generation/judging, DeepEval dataset gate, llama.cpp llama-server with --lora + shared base GGUF, local LoRA GGUF exports.

---

## Current-state findings from artifact review

### Artifact inventory

Latest Ollama datasets exist for all 4 NPCs:

| NPC | Train rows | Validation rows | Mean sanitizer quality | DeepEval gate | Training loss | Export |
|-----|------------|-----------------|------------------------|---------------|---------------|--------|
| history_guide | 117 | 15 | 83.2 | 2/2 pass | 1.0678 | exports/history_guide/history_guide-lora-f16.gguf |
| chef_assistant | 117 | 15 | 81.4 | 3/3 pass | 1.1283 | exports/chef_assistant/chef_assistant-lora-f16.gguf |
| astronomy_guide | 117 | 15 | 82.5 | 2/3 pass | 1.1100 | exports/astronomy_guide/astronomy_guide-lora-f16.gguf |
| fitness_coach | 117 | 15 | 84.2 | 5/5 pass | 1.0389 | exports/fitness_coach/fitness_coach-lora-f16.gguf |

Training/export happened cleanly for the May 18 Ollama run:
- all four latest runs are under outputs/{npc}/runs/20260518_fast-3b_llama3.2-3b_*;
- all four adapter GGUFs are about 48.66 MB;
- losses are much better than the old Onyx/template baseline memories, but loss alone is not enough.

### Important problem: final eval artifacts are stale or incomplete

The newest persisted markdown reports for all four NPCs are dated/m-timed May 17, before the May 18 Ollama datasets/training artifacts:
- eval/reports/history_guide/eval_2026-05-17.md
- eval/reports/chef_assistant/eval_2026-05-17.md
- eval/reports/astronomy_guide/eval_2026-05-17.md
- eval/reports/fitness_coach/eval_2026-05-17.md

That means the console log `Astronomy complete ✅ — candidate win rate 20%` is not currently represented by the persisted report set I found. Do not make model-quality decisions until we rerun/persist the final evaluation for the four May 18 GGUFs.

### Dataset gate is too shallow

Current `./ucore dataset-eval` default is `--cases-per-category 1`, and the actual summaries only judged 2-5 cases per NPC. This is too small to validate 117-row datasets.

Specific issue found:
- astronomy_guide failed 1 refusal case: the row asks about life on other planets and the answer does not behave like a refusal/boundary response. It is educational and safe, but category-labeled `refusal`, so either the category is wrong or the refusal prompt contract is too vague.

### Eval harness currently over-penalizes normal answers

`scripts/evaluate.py` treats missing NPC name as a constraint violation for every response. That is not a real requirement in the current system prompts; normal useful answers should not have to say `HistoryGuide`, `ChefAssistant`, etc. every turn. This causes noisy `has_name` / `has_name_candidate` violations across almost every report.

Also, the heuristic winner fallback uses mostly sentence count + name mention + no AI disclaimer. That explains suspicious results where a short, vague candidate can beat a detailed baseline even when quality is lower.

### Generation quality pattern

The Ollama data is clean and generally on-topic, but mostly one-turn short answers. That fits the 1-3 sentence LLMUnity style, but it undertrains:
- follow-up dialogue;
- concrete tutoring steps;
- refusal boundaries;
- grounded subject specificity under broad questions;
- stable conversational voice.

The May 17 reports show candidates often win by being shorter rather than more informative. Examples: astronomy and fitness candidates beat base at 70%/60%, but candidate quality scores are lower and answers are often generic. Chef/history are weaker when compared against prior LoRA baselines.

---

## Target contracts

### Evaluation contract

1. Every production comparison must evaluate the latest exported adapter with:
   `--base-model Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf`
2. Every evaluation must write all three artifacts:
   - markdown report under eval/reports/{npc}/
   - html report under eval/reports/{npc}/
   - feedback JSON under eval/results/feedback/
3. Win rate alone is not enough. Track:
   - candidate wins / baseline wins / ties;
   - average usefulness score from judge;
   - constraint violations by real rule only;
   - concept/category weak spots;
   - examples where candidate is shorter but less specific.
4. Do not require NPC-name mention on every answer. Only identity prompts should require self-identification.

### Dataset gate contract

1. Gate all five categories for every NPC.
2. Minimum gate size: 3 cases per category for quick local iteration; 5 cases per category before training.
3. A category-labeled refusal row must actually refuse, redirect, or boundary-set.
4. A validation split must remain first-class and must not be hidden by sanitizer manifests.
5. Sanitizer manifest must preserve `technique=ollama`, `total_train=117`, and `total_validation=15` or explicitly link the validation manifest.

### Generation contract

1. Keep 1-3 sentence answers, but require one concrete subject-specific fact per teaching/dialogue answer.
2. Add multi-turn examples for at least 20-30% of rows.
3. Add refusal templates per NPC with explicit boundaries and safe redirects.
4. Reduce generic filler like “once you understand this, everything falls into place.”
5. Keep validation examples out of training and use them for eval prompts.

---

## Phase 1: Reproduce and persist the real May 18 evaluation

### Task 1: Confirm latest artifacts point to May 18 LoRAs

Objective: avoid comparing stale exports.

Files:
- Read: outputs/{npc}/latest or latest runs under outputs/{npc}/runs/
- Read: exports/{npc}/{npc}-lora-f16.gguf

Run:
```bash
for npc in history_guide chef_assistant astronomy_guide fitness_coach; do
  echo "== $npc =="
  ls -lh exports/$npc/${npc}-lora-f16.gguf
  find outputs/$npc/runs -maxdepth 2 -name training_metrics.json -printf '%T@ %p\n' | sort -nr | head -1
  cat $(find outputs/$npc/runs -maxdepth 2 -name training_metrics.json -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)
done
```

Expected: May 18 runs and the four losses listed above.

### Task 2: Re-run eval against the base model for astronomy and fitness first

Objective: reproduce the user-observed 20% astronomy win rate and persist the report.

Run:
```bash
BASE="Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf"
./ucore evaluate \
  --baseline "$BASE" \
  --candidate exports/astronomy_guide/astronomy_guide-lora-f16.gguf \
  --base-model "$BASE" \
  --spec subjects/astronomy_guide.json \
  --val-data subjects/datasets/astronomy_guide/ollama/validation.jsonl \
  --report-html \
  --feedback-json eval/results/feedback/astronomy_guide_ollama_may18_feedback.json

./ucore evaluate \
  --baseline "$BASE" \
  --candidate exports/fitness_coach/fitness_coach-lora-f16.gguf \
  --base-model "$BASE" \
  --spec subjects/fitness_coach.json \
  --val-data subjects/datasets/fitness_coach/ollama/validation.jsonl \
  --report-html \
  --feedback-json eval/results/feedback/fitness_coach_ollama_may18_feedback.json
```

Expected: new mtime under eval/reports/{npc}/ and feedback JSON exists.

### Task 3: Re-run eval against prior LoRA baselines for history and chef

Objective: compare new Ollama LoRAs against the known stronger local LoRA baselines, not just the base model.

Run:
```bash
BASE="Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf"
./ucore evaluate \
  --baseline exports/history_guide/history_guide_v2-lora-f16.gguf \
  --candidate exports/history_guide/history_guide-lora-f16.gguf \
  --base-model "$BASE" \
  --spec subjects/history_guide.json \
  --val-data subjects/datasets/history_guide/ollama/validation.jsonl \
  --report-html \
  --feedback-json eval/results/feedback/history_guide_ollama_may18_feedback.json

./ucore evaluate \
  --baseline exports/chef_assistant/chef_assistant_v2-lora-f16.gguf \
  --candidate exports/chef_assistant/chef_assistant-lora-f16.gguf \
  --base-model "$BASE" \
  --spec subjects/chef_assistant.json \
  --val-data subjects/datasets/chef_assistant/ollama/validation.jsonl \
  --report-html \
  --feedback-json eval/results/feedback/chef_assistant_ollama_may18_feedback.json
```

Expected: new reports replace console-only impressions with persisted results.

---

## Phase 2: Fix eval validity before training again

### Task 4: Make name requirement prompt-aware

Objective: stop counting missing NPC name as a violation except on identity prompts.

Files:
- Modify: scripts/evaluate.py
- Test: add or update tests for `check_contains_name` / evaluation metrics if test coverage exists.

Implementation target:
- Replace unconditional `check_contains_name(response, spec.get("npc_name"))` with a function that only requires the name when the question asks identity/self-introduction, e.g. contains `who are you`, `what is your name`, or starts with a direct NPC-name identity prompt.

Verification:
```bash
python -m py_compile scripts/evaluate.py
./ucore evaluate --help
```

### Task 5: Add usefulness/specificity signals to the winner logic

Objective: prevent short generic answers from winning just because they obey 1-3 sentence limits.

Files:
- Modify: scripts/evaluate.py

Implementation target:
- Add a simple subject-specificity score:
  - counts domain terms from spec concepts/knowledge;
  - penalizes generic filler phrases;
  - rewards answer containing at least one concrete noun/fact from the expected validation answer when available.
- Only use heuristic fallback when no LLM judge result exists.
- If judge says tie, preserve tie unless one side violates hard rules or is empty.

Verification:
```bash
python -m py_compile scripts/evaluate.py
./ucore evaluate --baseline <base> --candidate <adapter> --base-model <base> --spec subjects/fitness_coach.json --val-data subjects/datasets/fitness_coach/ollama/validation.jsonl --num-questions 3
```

Expected: no universal has_name violations; winner reasoning reflects specificity/usefulness.

---

## Phase 3: Strengthen dataset gates

### Task 6: Raise default dataset gate coverage

Objective: DeepEval should not pass a production dataset after judging only 2-5 rows.

Files:
- Modify: scripts/dataset_eval.py
- Possibly modify: ucore command wrapper if it hardcodes cases.

Implementation target:
- Keep CLI default at quick mode only if explicitly `--quick`.
- Production default: `--cases-per-category 5`.
- Ensure summaries always include all five categories, even if a category was not sampled.

Verification:
```bash
./ucore dataset-eval subjects/fitness_coach.json --technique ollama --cases-per-category 5 --soft-fail
```

Expected: about 25 total cases, 5 categories represented.

### Task 7: Add refusal-category structural checks before DeepEval

Objective: catch mislabeled refusal rows locally before spending judge calls.

Files:
- Modify: scripts/sanitize_dataset.py or add a small validator used by dataset-eval.

Implementation target:
For rows with metadata.category == `refusal`, require at least one of:
- explicit boundary: “I can’t”, “I won’t”, “not safe”, “outside what I cover”, “cannot confirm”;
- safe redirect: “I can help with”, “instead”, “let’s focus on”;
- myth/conspiracy correction for domain-specific unsafe claims.

Verification:
```bash
./ucore sanitize subjects/datasets/astronomy_guide/ollama/train.jsonl \
  --output /tmp/astronomy_clean_check.jsonl \
  --strict-canonical --require-complete-metadata
```

Expected: current astronomy solar-system life row is flagged or category-fixed.

### Task 8: Fix sanitizer manifest metadata

Objective: preserve validation/provenance information after sanitize.

Files:
- Modify: scripts/sanitize_dataset.py

Implementation target:
- If input is `subjects/datasets/{npc}/{technique}/train.jsonl`, infer technique from parent directory safely.
- Preserve previous generation manifest fields or link to `generation_manifest`.
- Count sibling `validation.jsonl` rows and include `statistics.total_validation`.

Verification:
```bash
./ucore sanitize subjects/datasets/history_guide/ollama/train.jsonl \
  --output /tmp/history_clean_check.jsonl \
  --strict-canonical --require-complete-metadata
python - <<'PY'
import json
m=json.load(open('subjects/datasets/history_guide/ollama/train_manifest.json'))
assert m['technique'] == 'ollama'
assert m['statistics']['total_validation'] == 15
PY
```

---

## Phase 4: Improve Ollama generation

### Task 9: Add multi-turn generation mode

Objective: teach the LoRA actual conversational behavior, not only one-shot answers.

Files:
- Modify: scripts/generate_dataset_ollama.py

Implementation target:
- Add `--multi-turn-ratio` default 0.25 for ollama production generation.
- For selected examples, generate user/assistant/user/assistant sequences.
- Keep each assistant turn within 1-3 sentences.
- Metadata: `generator_params.multi_turn=true`, `turn_count`.

Verification:
```bash
./ucore generate subjects/astronomy_guide.json --technique ollama --dry-run
./ucore validate-spec subjects/astronomy_guide.json --generation-ready
```

### Task 10: Add category-specific prompt templates

Objective: make generated rows match category semantics.

Files:
- Modify: scripts/generate_dataset_ollama.py

Implementation target:
- `identity`: must answer who/role/teaching style.
- `teaching`: must include one concrete fact, one concise explanation.
- `dialogue`: must handle confusion/follow-up naturally.
- `quest`: must set up an interactive mini-task.
- `refusal`: must boundary-set and redirect.

Verification:
Generate 10-row dry sample or temporary output, then inspect examples for all categories.

### Task 11: Add anti-generic cleanup rules

Objective: remove low-information phrases that won eval only by brevity.

Files:
- Modify: scripts/sanitize_dataset.py or generation cleaner in scripts/generate_dataset_ollama.py

Implementation target:
Flag/rewrite rows dominated by:
- “once you understand this, everything falls into place”
- “let me tell you something about it”
- “this is really important to understand” without a concrete fact
- broad restatements of the question

Verification:
```bash
python - <<'PY'
from pathlib import Path
bad=['once you understand','let me tell you something about it','everything falls into place']
for p in Path('subjects/datasets').glob('*/ollama/train_clean.jsonl'):
    txt=p.read_text().lower()
    print(p, {b: txt.count(b) for b in bad})
PY
```

Expected: zero or near-zero bad phrase hits after regeneration.

---

## Phase 5: Regenerate only the weak categories, then retrain

### Task 12: First target astronomy refusal

Objective: fix the one observed hard dataset failure before broad retraining.

Run:
```bash
./ucore generate subjects/astronomy_guide.json --technique ollama --categories refusal --temperature 0.6
./ucore sanitize subjects/datasets/astronomy_guide/ollama/train.jsonl \
  --output subjects/datasets/astronomy_guide/ollama/train_clean.jsonl \
  --strict-canonical --require-complete-metadata
./ucore dataset-eval subjects/astronomy_guide.json --technique ollama --cases-per-category 5
```

Expected: astronomy refusal category passes.

### Task 13: Use feedback JSON to target weak concepts for each NPC

Objective: avoid blindly regenerating all rows.

Run after Phase 1 eval artifacts exist:
```bash
./ucore feedback subjects/history_guide.json --feedback-json eval/results/feedback/history_guide_ollama_may18_feedback.json --auto
./ucore feedback subjects/chef_assistant.json --feedback-json eval/results/feedback/chef_assistant_ollama_may18_feedback.json --auto
./ucore feedback subjects/astronomy_guide.json --feedback-json eval/results/feedback/astronomy_guide_ollama_may18_feedback.json --auto
./ucore feedback subjects/fitness_coach.json --feedback-json eval/results/feedback/fitness_coach_ollama_may18_feedback.json --auto
```

Important 6GB VRAM rule: unload Ollama before training.

Run:
```bash
curl http://localhost:11434/api/generate -d '{"model":"qwen2.5:7b","keep_alive":0}'
```

### Task 14: Retrain one NPC at a time after gates pass

Objective: keep GPU memory stable and isolate regressions.

Run:
```bash
for npc in astronomy_guide fitness_coach history_guide chef_assistant; do
  ./ucore train subjects/$npc.json --technique ollama --preset fast-3b --export-gguf
  ./ucore smoke-test exports/$npc/${npc}-lora-f16.gguf --spec subjects/$npc.json
  # run eval command from Phase 1 for that npc before moving to the next one
done
```

Expected: no OOM, new adapter GGUF, new eval report per NPC.

---

## Acceptance criteria

1. Fresh May 18+ eval artifacts exist for all four NPCs and match the console summaries.
2. `dataset-eval --cases-per-category 5` passes for all four NPCs across all five categories.
3. `evaluate.py` no longer reports missing NPC name as a universal violation.
4. Astronomy refusal failure is fixed.
5. Validation split is represented correctly in manifests.
6. Candidate win rate is interpreted with specificity/usefulness, not just brevity.
7. Retraining happens only after the dataset gate passes.
8. Final deployed candidates should meet:
   - no hard safety/refusal failures;
   - candidate win/tie rate >= 70% against relevant baseline;
   - candidate direct win rate improves over the currently persisted baseline for each NPC;
   - no repeated generic filler patterns in sampled outputs.

---

## Immediate next 3 actions

1. Re-run and persist final eval for astronomy_guide and fitness_coach against the base GGUF, because current local reports are stale relative to May 18 training.
2. Patch `scripts/evaluate.py` so `has_name` is identity-prompt-only and not a universal constraint.
3. Raise dataset gate coverage to 5 cases/category and fix the astronomy refusal-row failure before any new training.

---

## Resume protocol

Current phase status: artifact review complete; implementation not started.

Next phase entry commands:
```bash
BASE="Assets/StreamingAssets/Models/llama-3.2-3b-instruct-q4_k_m.gguf"
./ucore evaluate --baseline "$BASE" --candidate exports/astronomy_guide/astronomy_guide-lora-f16.gguf --base-model "$BASE" --spec subjects/astronomy_guide.json --val-data subjects/datasets/astronomy_guide/ollama/validation.jsonl --report-html --feedback-json eval/results/feedback/astronomy_guide_ollama_may18_feedback.json
```

Done-when for Phase 1: all four May 18 eval feedback JSONs and reports exist and their candidate win rates are summarized in one table.
