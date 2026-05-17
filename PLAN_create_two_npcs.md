# Plan: Create 2 New NPCs — Astronomy Guide & Fitness Coach

## NPC Selection

| NPC | Key | Subject | Why This Works |
|-----|-----|---------|----------------|
| **Astronomy Guide** | `astronomy_guide` | Space, stars, planets, telescopes, astronomy history | Rich factual knowledge, clear Q&A structure, strong game NPC utility (star-gazing, space exploration settings) |
| **Fitness Coach** | `fitness_coach` | Exercise science, nutrition, workout programming, wellness | Ubiquitous game NPC (trainer, gym), well-structured reference material, safety boundaries are clear |

Both subjects have abundant public knowledge for reference docs and are totally distinct from the existing pair (history / culinary).

---

## Pipeline Overview (Per NPC)

For each NPC, we run the 5-stage pipeline:

1. **Scaffold** → `./ucore init` creates spec, primer stub, directories
2. **Write Reference Doc** → Fill `subjects/reference_docs/{npc_key}_primer.md` with domain content
3. **Validate Spec** → `./ucore validate-spec`
4. **Generate Dataset** → `./ucore generate` (template technique — fast, no Onyx or Ollama needed for v1)
5. **Sanitize** → `./ucore sanitize`
6. **Train & Export** → `./ucore train --preset smoke` (smoke preset = fast, low VRAM test)
7. **Validate Config** → `./ucore validate-config` to verify resolved config
8. **Evaluate** → `./ucore evaluate` (quick smoke test)

---

## Step-by-Step Execution Plan

### Phase 1: Scaffold Both NPCs

```bash
# Astronomy Guide
./ucore init astronomy_guide --subject "Astronomy and space science" --name "AstronomyGuide"

# Fitness Coach
./ucore init fitness_coach --subject "Fitness, exercise science, and nutrition" --name "FitnessCoach"
```

This creates per NPC:
- `subjects/{npc_key}.json` — full spec with system prompt, research queries, dataset sizes (8/32/16/8/8 = 72 total)
- `subjects/reference_docs/{npc_key}_primer.md` — stub reference doc
- `subjects/datasets/{npc_key}/onyx/` — production dataset dir
- `subjects/datasets/{npc_key}/template/` — fast/smoke dataset dir
- `outputs/{npc_key}/runs/` — training output dir
- `exports/{npc_key}/` — GGUF export dir

### Phase 2: Write Reference Docs

Edit each `*_primer.md` with:

**astronomy_guide_primer.md** — ~40 lines covering:
- Solar System (Sun, planets, moons, asteroids)
- Stars & galaxies (types, life cycle, Milky Way, classification)
- Observational astronomy (telescopes, constellations, Messier objects)
- Space exploration (missions, space stations, rovers)
- Key astronomy concepts (light years, redshift, habitable zone)

**fitness_coach_primer.md** — ~40 lines covering:
- Exercise science (muscle groups, progressive overload, recovery)
- Major training modalities (strength, cardio, flexibility, HIIT)
- Nutrition fundamentals (macros, micros, hydration, timing)
- Common programming (push/pull/legs, full body, split routines)
- Safety & form (injury prevention, warmup/cool-down, listen to your body)

### Phase 3: Validate Specs

```bash
./ucore validate-spec subjects/astronomy_guide.json
./ucore validate-spec subjects/fitness_coach.json
```

Fix any schema violations.

### Phase 4: Generate Datasets (Template Technique)

```bash
# Astronomy Guide — template (fast, deterministic)
./ucore generate subjects/astronomy_guide.json --technique template

# Fitness Coach — template
./ucore generate subjects/fitness_coach.json --technique template
```

This generates `subjects/datasets/{npc_key}/template/train.jsonl` with 72 examples each.

**Template technique**: Uses CATEGORY_TEMPLATES from generate_dataset.py — fills in identity/teaching/dialogue/quest/refusal categories with the NPC's spec data. No external API or Onyx needed. Fast execution (~seconds).

### Phase 5: Sanitize Datasets

```bash
# Astronomy Guide
./ucore sanitize subjects/datasets/astronomy_guide/template/train.jsonl \
  --output subjects/datasets/astronomy_guide/template/train_clean.jsonl

# Fitness Coach
./ucore sanitize subjects/datasets/fitness_coach/template/train.jsonl \
  --output subjects/datasets/fitness_coach/template/train_clean.jsonl
```

### Phase 6: Train & Export (Smoke Preset)

```bash
# Astronomy Guide (smoke = r=8, a=16, 1 epoch — ~minutes)
./ucore train subjects/astronomy_guide.json --technique template --preset smoke --export-gguf

# Fitness Coach
./ucore train subjects/fitness_coach.json --technique template --preset smoke --export-gguf
```

Each produces:
- LoRA adapter at `outputs/{npc_key}/runs/{run_id}/`
- GGUF at `exports/{npc_key}/{npc_key}-lora-f16.gguf`

### Phase 7: Validate Resolved Config

```bash
./ucore validate-config --spec subjects/astronomy_guide.json --preset smoke
./ucore validate-config --spec subjects/fitness_coach.json --preset smoke
```

### Phase 8: Quick Smoke Test

```bash
./ucore smoke exports/astronomy_guide/astronomy_guide-lora-f16.gguf --spec subjects/astronomy_guide.json
./ucore smoke exports/fitness_coach/fitness_coach-lora-f16.gguf --spec subjects/fitness_coach.json
```

### Phase 9: Evaluate

```bash
./ucore evaluate --model exports/astronomy_guide/astronomy_guide-lora-f16.gguf \
  --spec subjects/astronomy_guide.json --num-questions 5

./ucore evaluate --model exports/fitness_coach/fitness_coach-lora-f16.gguf \
  --spec subjects/fitness_coach.json --num-questions 5
```

---

## Key Decision: Template vs Onyx

| Technique | When to Use | Time |
|-----------|------------|------|
| **Template** | First pass, smoke test, validation | Seconds per NPC |
| **Onyx** (RAG-grounded) | Production-quality dataset | Minutes per NPC + Onyx Docker required |

**Plan**: Start with `template` technique for both NPCs to validate the full pipeline end-to-end. After verifying the pipeline works, optionally regenerate with `onyx` technique for production-quality data.

If Onyx Docker is available (port 9000), upgrade to Onyx:
```bash
./ucore generate subjects/astronomy_guide.json --technique onyx
./ucore train subjects/astronomy_guide.json --technique onyx --preset fast-3b --export-gguf
```

---

## Resource Estimates

| NPC | Stage | Estimated Time | VRAM |
|-----|-------|---------------|------|
| Scaffold + Write docs | Phase 1-3 | ~15 min manual | N/A |
| Generate (template) | Phase 4 | ~5 sec | N/A |
| Sanitize | Phase 5 | ~2 sec | N/A |
| Train (smoke preset) | Phase 6 | ~5-10 min | ~3.5 GB |
| Export GGUF | Phase 6 | ~2 min | ~2 GB |
| Validate + Smoke + Eval | Phase 7-9 | ~5 min | ~3 GB |
| **Total per NPC** | | **~20-30 min** | |

---

## Success Criteria

- [ ] Both NPC specs validated successfully
- [ ] Template datasets generated (72 examples each)
- [ ] Datasets sanitized without errors
- [ ] Training completes with `smoke` preset (no OOM)
- [ ] GGUF exported (~47 MB each)
- [ ] Smoke test passes (model loads and responds)
- [ ] Audit check passes: `./ucore audit check`

---

## Rollback / Cleanup

If anything goes wrong:
```bash
# Remove an NPC and all its artifacts
rm -rf subjects/astronomy_guide.json
rm -rf subjects/reference_docs/astronomy_guide_primer.md
rm -rf subjects/datasets/astronomy_guide/
rm -rf outputs/astronomy_guide/
rm -rf exports/astronomy_guide/
```
