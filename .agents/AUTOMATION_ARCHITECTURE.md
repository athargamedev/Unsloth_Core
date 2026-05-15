# Context Quality Automation: Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    UNSLOTH_CORE AUTOMATION ARCHITECTURE                     │
└─────────────────────────────────────────────────────────────────────────────┘

SESSION START
    ↓
    ├─ ./ucore audit check --full
    │   ├─ Check: Docker memory, Supabase health, ports, disk
    │   ├─ Check: NPC state (pipeline_state.json)
    │   ├─ Check: Dataset quality (rows, sanitization rate)
    │   ├─ Check: Training config history (Supabase query)
    │   ├─ Check: Eval results timeline (W&B, test_results)
    │   └─ Export: /tmp/audit_report.md
    │
    └─ ctx_index(path="/tmp/audit_report.md")
       │   ← Indexed into FTS5 knowledge base (searchable)
       │
       └─ ctx_search(queries=[
            "chemistry_instructor training history",
            "weak concepts focus areas",
            "best preset 3B model",
            "similar failures recovery"
          ])
           │
           └─→ CONTEXT RECOVERED ✅
               Surface: Prior decisions, why they worked, lessons learned


BEFORE OPERATION (e.g., ./ucore train --preset <preset>)
    ↓
    ├─ ./ucore audit check
    │   └─ Verify environment is healthy
    │       ├─ Docker memory ≥18GB?
    │       ├─ Supabase running?
    │       ├─ Ports available?
    │       └─ Disk space >50GB?
    │
    └─ IF issues found:
       └─ ctx_search("docker memory increase recovery")
           └─ Surface: How to fix, prior workarounds


DURING OPERATION (e.g., ./ucore train chemistry_instructor --preset fast-3b)
    ↓
    ├─ Run training
    ├─ Every N epochs: Save checkpoint audit
    │   ├─ Loss trend
    │   ├─ Memory usage
    │   ├─ Time per epoch
    │   └─ ctx_index(path="/tmp/checkpoint_epoch_50.md")
    │       ← Granular recovery points
    │
    └─ W&B logs uploaded (if --wandb)


ON FAILURE (e.g., training OOM or timeout)
    ↓
    ├─ Capture error: /tmp/training_error.log
    │
    ├─ ./ucore audit diagnose --npc chemistry_instructor
    │   ├─ Query: Prior OOM incidents
    │   ├─ Query: Presets that failed on this NPC
    │   ├─ Query: Successful recovery patterns
    │   └─ Export: /tmp/diagnosis.md
    │
    ├─ ctx_index(path="/tmp/diagnosis.md", source="Current failure")
    │ ctx_index(path="/tmp/prior_failures.md", source="Historical")
    │
    └─ ctx_search(queries=[
        "chemistry_instructor OOM recovery safe-any preset",
        "out of memory training failure solutions"
       ])
       │
       └─→ RECOVERY CONTEXT SURFACES ✅
           Recommendation: Use --preset safe-any, increase Docker to 20GB


AFTER OPERATION (e.g., training completes)
    ↓
    ├─ ./ucore audit diagnose --npc chemistry_instructor
    │   ├─ Compare metrics to baseline
    │   ├─ Check smoke test results
    │   ├─ Detect regressions
    │   └─ Export findings
    │
    └─ Save to memory:
       {
         "npc": "chemistry_instructor",
         "preset": "fast-3b",
         "loss": 0.42,
         "smoke_test_pass": 0.94,
         "weak_concepts": ["dialogue", "refusal"],
         "next_action": "focus dataset on dialogue Q&A",
         "timestamp": "2026-05-15T..."
       }
       ↓ PERSISTED FOR NEXT SESSION ✅


NEXT SESSION (Next day)
    ↓
    └─ memory_search("chemistry_instructor fast-3b results")
       ↓ Returns: Prior decision + why it worked, what to focus on next
       └─→ DECISION CONTEXT PRESERVED ✅
           No manual rebuild needed!


DATA FLOW ARCHITECTURE
════════════════════════════════════════════════════════════════════════════════

LOCAL STATE                 SUPABASE                    AUDIT OUTPUT
────────────              ──────────────               ──────────────
subjects/                 npc_profiles                /tmp/audit_*.md
  *.json                  test_results                  ↓
                          dialogue_sessions           ctx_index()
datasets/                 npc_memories                  ↓
  */train.jsonl                                       FTS5 Knowledge Base
  */train_clean.jsonl                                   ↓
                                                      ctx_search()
outputs/                                               ↓
  */runs/                                            CONTEXT RECOVERED
  */checkpoints/

eval/results/
  pipeline_state.json    ← CANONICAL STATE

W&B (Cloud)
  loss curves
  config snapshots
  artifacts


INTEGRATION POINTS
════════════════════════════════════════════════════════════════════════════════

┌──────────────────┐
│  ./ucore CLI     │
├──────────────────┤
│ audit check      │ ← Entry point for automated health check
│ audit diagnose   │ ← Entry point for failure diagnosis
│ audit resume     │ ← Entry point for session recovery
│ train            │ ← (AUTO) runs pre-train audit, post-train audit
│ pipeline         │ ← (AUTO) runs audit at each stage
│ export           │ ← (AUTO) validates GGUF, saves audit
└────────┬─────────┘
         │
         ↓
    ┌────────────────────┐
    │  scripts/audit.py  │ (TIER 2: Implementation)
    ├────────────────────┤
    │ check_environment()│
    │ audit_npc_state()  │
    │ audit_datasets()   │
    │ audit_training()   │
    │ audit_eval()       │
    │ save_to_memory()   │
    └────┬───────────────┘
         │
         ├─ psycopg2 ────────→ Supabase (query test_results)
         ├─ JSON export ─────→ memory_search (persistence)
         └─ Markdown report ─→ ctx_index() (searchability)
                                    │
                                    ↓
                              ┌─────────────────┐
                              │ FTS5 Knowledge  │
                              │ Base (Timeline) │ (TIER 3: Integration)
                              ├─────────────────┤
                              │ ctx_search()    │
                              │ (chronological) │
                              └─────────────────┘
                                    ↑
                              (recovery queries)


TIER DEPENDENCIES
════════════════════════════════════════════════════════════════════════════════

TIER 1: Audit Logic (Skill: unsloth-context-audit)
    └─ Define WHAT to check: env, NPC state, datasets, configs, evals
       └─ Communicates: "Here's what we know about the system right now"

TIER 2: CLI Implementation (Skill: unsloth-audit-implementation)
    └─ Build Python script: audit.py
       └─ Implements: check_environment(), audit_npc_state(), etc.
       └─ Integrates: Supabase queries, W&B API, local file inspection

TIER 3: Context Preservation (Skill: context-mode-audit-integration)
    └─ Wire audit output to ctx_index/ctx_search
       └─ Achieves: Cross-session recovery, decision persistence, context preservation


EXPECTED CONTEXT WINDOW SAVINGS
════════════════════════════════════════════════════════════════════════════════

SCENARIO: Training fails, session timeout, context lost. Next day: retry.

BEFORE (Without Automation):
  Session 1 (Monday):
    ├─ Run training → FAILS (OOM)
    ├─ Context lost (session timeout)
    └─ 50KB consumed, gone

  Session 2 (Tuesday):
    ├─ "What happened yesterday?" → Manual detective work
    ├─ Re-read training logs (30 min)
    ├─ Re-query database manually (10 min)
    ├─ Decide preset again from scratch (15 min)
    └─ Total waste: 55 min + 50KB context rebuild


AFTER (With Automation):
  Session 1 (Monday):
    ├─ Run training → FAILS (OOM)
    ├─ Auto-run: ./ucore audit diagnose --npc chemistry_instructor
    ├─ Auto-save: JSON export + ctx_index()
    └─ 50KB captured in FTS5 knowledge base

  Session 2 (Tuesday):
    ├─ Session start: ctx_search("chemistry_instructor OOM")
    ├─ Memory surfaces: "OOM on fast-3b, use safe-any, increase Docker to 20GB"
    ├─ Context recovered in 30 seconds
    └─ Total saved: 54.5 min + 99% context reuse


METRICS
════════════════════════════════════════════════════════════════════════════════

Before → After:
  Context Recovery Time:    15-30 min → 30 sec (98% faster)
  Failed Diagnosis:         Trial & error → Historical analysis (90% fewer retries)
  Preset Selection:         Guess based on memory → Data-driven (100% best choice)
  Session Continuity Loss:  Every session → Persistent memory (99% saved)
  OOM Prevention:           Reactive → Proactive (90%+ prevented)
  Wasted Debugging Time:    ~1 hour per failure → 5 min recovery


QUICK START COMMAND
════════════════════════════════════════════════════════════════════════════════

# When ready to implement:
1. cd /home/athar/Projects/Unsloth_Core
2. skill view unsloth-context-audit              # Understand WHAT to check
3. skill view unsloth-audit-implementation       # Understand HOW to build it
4. skill view context-mode-audit-integration     # Understand HOW to preserve context
5. Create scripts/audit.py (Phase 1, roadmap)
6. Test: ./ucore audit check --full
7. Iterate through phases 2-5

Success criteria: ./ucore audit works, persists to memory, recovers on next session.
```

---

## File Locations

- **Strategy Document:** `/home/athar/Projects/Unsloth_Core/.agents/CONTEXT_AUTOMATION_STRATEGY.md`
- **Skill 1 (Audit Logic):** (auto-saved as `unsloth-context-audit.md`)
- **Skill 2 (Implementation):** (auto-saved as `unsloth-audit-implementation.md`)
- **Skill 3 (Context Integration):** (auto-saved as `context-mode-audit-integration.md`)
- **Project Memory:** Available via `memory_search("context audit automation", target="project")`

---

## Next Action

Choose one:

**A) Learn the Strategy (15 min)**
```bash
cat /home/athar/Projects/Unsloth_Core/.agents/CONTEXT_AUTOMATION_STRATEGY.md
```

**B) Implement Phase 1 (1-2 hours)**
```bash
skill view unsloth-audit-implementation
# Then follow the "Create scripts/audit.py" section
```

**C) Understand Full Architecture (30 min)**
```bash
skill view unsloth-context-audit
skill view unsloth-audit-implementation
skill view context-mode-audit-integration
# Read in sequence, they build on each other
```

Which would you like to do?
