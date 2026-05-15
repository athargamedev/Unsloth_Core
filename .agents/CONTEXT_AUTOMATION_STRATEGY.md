# Unsloth_Core: Context Quality Automation Strategy

**Date:** 2026-05-15  
**Purpose:** Prevent context loss across sessions and automate health checks to improve development velocity  
**Status:** Strategy document → Skills created → Ready for implementation

---

## 🎯 Problem Statement

Your Unsloth_Core workflow involves:
- **4 active NPCs** with complex interdependencies
- **5-stage pipeline** (generation → sanitization → training → export → eval)
- **Multiple tools** (NotebookLM, llama.cpp, Supabase, W&B, Docker, Onyx)
- **Long-running operations** (training takes 2-4 hours, eval takes 1+ hour)
- **State spread across multiple systems**: Local files, Supabase DB, W&B, Docker volumes, eval/ directory

**Context quality issues:**
1. ❌ Session ends → new session loses "why did we choose this preset?"
2. ❌ Training fails → manual detective work to find similar prior failures
3. ❌ Dataset changes → no tracking of what changed, why, impact
4. ❌ Port/config misalignment → restarts waste time debugging environment
5. ❌ Memory pressure → Docker OOM kills containers, context about state lost

---

## ✅ Solution: 3-Tier Automation

### Tier 1: **Project Health Audit** (Immediate diagnostics)
**Skill:** `unsloth-context-audit`

Automated checkups that run:
- ✅ Before major operations (`./ucore train`, `./ucore pipeline`)
- ✅ After failures (diagnose why, surface prior similar failures)
- ✅ At session start (what was being worked on? what's pending?)

**What it checks:**
```
Environment:    Docker memory, Supabase health, ports, disk space
NPC State:      Status, weak concepts, pending feedback from eval
Dataset QA:     Row counts, sanitization rate, format validation
Training Config: Preset alignment, model size appropriateness
Eval Timeline:  Loss trends, smoke test pass rate, regressions
```

**Output:** 
- Console report (readable immediately)
- JSON state file (queryable)
- Memory entries (persistent across sessions)

### Tier 2: **Audit Implementation** (CLI tooling)
**Skill:** `unsloth-audit-implementation`

Create `./ucore audit` command suite:
```bash
./ucore audit check           # Is environment healthy? (5 sec)
./ucore audit check --full    # Full audit (30 sec)
./ucore audit diagnose --npc chemistry_instructor  # Why did it fail?
./ucore audit resume          # Rebuild session context from disk state
```

**Integrations:**
- Supabase queries (psycopg2) for historical training results
- W&B API queries for past config + metrics
- Local file inspection (datasets/, outputs/, eval/)
- Auto-export to JSON for memory persistence

### Tier 3: **Context Mode Integration** (Cross-session recovery)
**Skill:** `context-mode-audit-integration`

Use context-mode tools to:
```
Audit output (.md) → ctx_index → searchable, persistent
Supabase queries → indexed as timeline (chronological)
Prior failures → surface on demand via ctx_search
Decision history → "why did we pick fast-3b for 3B models?"
```

**Workflow:**
```
Session 1: Training run
  ↓ saves audit to /tmp/audit.md
  ↓ ctx_index(path="/tmp/audit.md")

Session 2 (next day): New training attempt
  ↓ run ./ucore audit check --full
  ↓ ctx_search("chemistry_instructor preset recommendation")
  ↓ surfaces: "fast-3b gave 0.42 loss vs smoke 0.51, use fast-3b"
  ↓ context recovered, no manual rebuild needed
```

---

## 📊 Expected Impact

| Issue | Before | After | Impact |
|-------|--------|-------|--------|
| **Context recovery time** | 15-30 min manual | 30 sec auto | 99% faster |
| **Failed training diagnosis** | Trial & error | Historical analysis | 80% fewer retries |
| **Preset selection** | Guess based on memory | Data-driven comparison | Best preset every time |
| **Session continuity** | Lost between sessions | Persisted in memory | No context rebuild |
| **Memory pressure issues** | No early warning | Pre-op health check | OOM prevented proactively |
| **Dataset quality drift** | Undetected | QA audit before regen | 100+ rows minimum enforced |

---

## 🛠️ Implementation Roadmap

### Phase 1: Audit CLI (1-2 hours)
- [ ] Create `scripts/audit.py` (main class with 5 check methods)
- [ ] Add `audit` command to `ucore` CLI
- [ ] Test: `./ucore audit check`, `./ucore audit check --full`
- [ ] Test: `./ucore audit diagnose --npc chemistry_instructor`

**Output:** Audits work, can run manually

### Phase 2: Supabase Integration (30 min)
- [ ] Connect psycopg2 to Supabase DB
- [ ] Query test_results table for best preset per NPC
- [ ] Export prior failures as diagnostic hints

**Output:** Audit knows what worked before

### Phase 3: Memory Persistence (30 min)
- [ ] Add `audit.save_to_memory()` export to JSON
- [ ] Create memory entry template
- [ ] Test memory recovery: `memory_search("chemistry_instructor preset")`

**Output:** Context persists across sessions

### Phase 4: Context-Mode Integration (1 hour)
- [ ] Wire audit output to `ctx_index(path="...")`
- [ ] Add `ctx_search(sort="timeline")` to session start
- [ ] Test end-to-end: Fail → diagnose → recover in next session

**Output:** Full cross-session context preservation

### Phase 5: Lifecycle Hooks (1 hour, optional but high-value)
- [ ] Pre-training: Auto-run `audit check`, prompt on issues
- [ ] Post-training: Auto-run `audit diagnose`, save to memory
- [ ] Post-eval: Auto-run `audit resume`, surface trends

**Output:** Zero-friction workflow, audits run automatically

---

## 📋 Key Metrics to Track

Once implemented, measure:

| Metric | Target | Benefit |
|--------|--------|---------|
| **Audit run time** | <30 sec (full) | No friction to run before operations |
| **Context recovery success rate** | >95% | Rarely need manual rebuild |
| **Preset recommendation accuracy** | >90% | Data-driven choices, fewer retries |
| **Dataset validation pass rate** | 100% | Never train on bad data |
| **OOM prevention rate** | 90%+ | Memory issues caught before training |

---

## 🚀 Getting Started

### Immediate Action (Today)
1. Read skill: `unsloth-context-audit` (understand the checkups)
2. Read skill: `unsloth-audit-implementation` (understand the tooling)
3. Read skill: `context-mode-audit-integration` (understand the context preservation)

### Next Session
1. Run Phase 1: Implement `scripts/audit.py` and CLI integration
2. Test: `./ucore audit check` works
3. Expand: Add Supabase queries

### Two Weeks
1. Full stack working (all 3 skills implemented)
2. Training workflow includes pre-op audit (Phase 5 hooks)
3. Context recovers automatically between sessions

---

## 💾 Memory Entries Created

This strategy has been saved to:
- **Project memory:** Core Unsloth_Core conventions, NPC data model, Supabase URLs
- **Skills:** 3 comprehensive skills covering audit, implementation, context integration

For future reference:
```
memory_search("unsloth context audit automation")
memory_search("npc training best practices", target="project")
memory_search("preset recommendation chemistry", target="project")
```

---

## Questions?

- **How do I run an audit?** → Read `unsloth-context-audit` skill
- **How do I implement it?** → Read `unsloth-audit-implementation` skill
- **How does it preserve context?** → Read `context-mode-audit-integration` skill
- **Where's the code?** → Start with Phase 1 of the roadmap above

---

**Next Step:** Implement Phase 1 (audit CLI). Estimated time: 1-2 hours. Start with `scripts/audit.py`.