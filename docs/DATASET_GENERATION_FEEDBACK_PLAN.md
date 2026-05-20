# Dataset Generation & Feedback Loop Plan for Unsloth_Core

This document captures the recommended improvement plan for NPC dataset generation, DeepEval validation, LoRA training, and Unity/Supabase runtime integration.

## Goal

Create a professional, reliable pipeline for `llama3.2-3b` LoRA adapter training using the production Ollama generator, with strong dataset structure, validation, and feedback loop support.

---

## 1. Spec Audit & Tightening

### Objective
Ensure the NPC spec is high-quality, Unity-ready, and not introducing downstream errors.

### Actions
- Review and tighten `system_prompt` rules.
  - Avoid open-ended citation requirements.
  - Prefer wording like: “If you mention evidence, keep it high-level and do not invent citations.”
- Lock down dialogue constraints for Unity.
  - Consider reducing `max_sentences` from `4` to `2-3`.
  - Consider reducing `max_characters` from `600` to `250-350` for UI consistency.
- Confirm refusal and boundary rules are explicit.
  - Keep: “NEVER speculate without labeling it as speculation.”
  - Add: “Do not invent quotes, dates, or unsourced facts.”
- Validate concept coverage.
  - Ensure `concepts` cover all training domains and conversational topics.
  - Add dialogue-friendly concepts if needed.
- Verify the reference primer.
  - Confirm it contains concrete examples, misconceptions, and evidence boundaries.
  - Confirm it is not too generic.

---

## 2. Generator / Dataset Structure Enhancements

### Objective
Use `generate_dataset_ollama.py` as the canonical production generator and improve dataset reliability.

### Actions
- Treat `generate_dataset_ollama.py` as the production dataset path.
- Strengthen generation prompt guardrails.
  - Enforce no markdown, no bullets, no AI disclaimers.
  - Enforce strict game UI text style.
- Improve validation split logic.
  - Replace random split with a category-stratified split.
  - Guarantee at least one validation example per category.
- Preserve and enrich metadata.
  - Ensure `dialogue_type` is populated for dialogue examples.
  - Ensure `boundary` is populated for refusal examples.
- Add pre-write quality checks.
  - Validate sentence count, character count, and scope adherence.
  - Reject generic filler responses.
- Keep error logging actionable.
  - Use `generation_errors.json` for failures.

---

## 3. Sanitize + DeepEval Gate

### Objective
Catch dataset issues before training and prevent poor data from reaching LoRA training.

### Actions
- Run the dataset sanitizer on production Ollama output.
  - `./ucore sanitize subjects/datasets/<npc>/ollama/train.jsonl`
- Run DeepEval on the cleaned dataset.
  - `DEEPEVAL_OLLAMA_MODEL=qwen3:latest ./ucore dataset-eval subjects/NPC_specs/<npc>.json --technique ollama`
- Inspect DeepEval artifacts.
  - `quality_summary.json`
  - `quality_failures.json`
  - `distribution_gaps`
- Fix failing categories or metrics.
  - Regenerate only failing rows or concepts.
  - Do not reduce thresholds unless failure is incorrect.

---

## 4. Train Reliable LoRA Adapters

### Objective
Produce a stable `llama3.2-3b` LoRA adapter that matches Unity runtime expectations.

### Actions
- Train from the cleaned Ollama dataset.
  - Use `./ucore train --preset fast-3b` for `llama3.2-3b`.
- Export the adapter GGUF.
- Validate training output with a small holdout.
- Keep the runtime training stack aligned.
  - Use the same base `llama3.2-3b` model in evaluation and export.

---

## 5. Unity + Supabase Runtime Alignment

### Objective
Ensure the runtime metadata and adapter path match the training dataset and NPC persona.

### Actions
- Update `npc_profiles` for the NPC.
  - Set `lora_path` to the exported adapter.
  - Store the same `system_prompt` used for training.
- Run `./ucore supabase-check --npc-key <npc>`.
- Verify `dialogue_sessions` and `npc_memories` work locally.
- Align training prompt rules with runtime prompt templates.
- Later, use actual session summaries for memory-grounded data.

---

## 6. Feedback Loop & Iteration

### Objective
Use evaluation outcomes to iterate on the dataset and adapter until stable.

### Actions
- Evaluate the trained adapter against a baseline.
- Identify weak concepts and categories.
- Regenerate and retrain on targeted examples.
  - Add more `teaching` examples for weak knowledge areas.
  - Add more `dialogue` examples for conversational weaknesses.
  - Add more `refusal` examples for boundary handling.
- Repeat generate → sanitize → evaluate → retrain.

---

## 7. Practical Unity/NPC Notes

### Objective
Optimize the dataset for actual in-game NPC dialogue, not just dataset metrics.

### Actions
- Keep responses short and UI-safe.
- Avoid markdown, bullets, or tables.
- Keep the NPC persona consistent across examples.
- Use game-specific `player_archetypes`.
- Treat `quest` as scenario practice, not generic teaching.

---

## Recommended Immediate Work Items

1. Patch `generate_dataset_ollama.py` to stratify validation splits and preserve category metadata.
2. Tighten `history_guide.json` prompts for Unity-safe length and citation behavior.
3. Re-run generation → sanitize → DeepEval.
4. Train and export the LoRA adapter.
5. Validate Supabase runtime metadata and adapter path.

---

## Notes

- The `history_guide` spec is not the primary failure point: the generated dataset already fulfills the contract.
- The main improvement areas are dataset validation, metadata quality, holdout split, and runtime alignment.
- This plan is intended to turn your existing pipeline into a more stable production workflow for Unity NPC dialogue.
