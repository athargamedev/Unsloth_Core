# Quick Reference: Audit CLI Commands

## Copy-Paste Commands

### Try it right now:
```bash
cd /home/athar/Projects/Unsloth_Core
./ucore audit check --full
```

### Daily use:

**Before training:**
```bash
./ucore audit check
```

**When training fails:**
```bash
./ucore audit diagnose --npc chemistry_instructor
```

**Session start recovery:**
```bash
./ucore audit resume
```

---

## Command Reference

| Command | Purpose | Speed |
|---------|---------|-------|
| `./ucore audit check` | Quick environment check | 5 sec |
| `./ucore audit check --full` | Full health audit | 30 sec |
| `./ucore audit diagnose --npc NAME` | Diagnose specific NPC + recommendations | 10 sec |
| `./ucore audit resume` | Session recovery (full audit) | 30 sec |

---

## What Each Command Shows

### `audit check` (Quick)
```
Environment Health: [score]%
  ✅/❌ Docker memory
  ✅/❌ Supabase connectivity
  ✅/❌ Ports available
  ✅/❌ Disk space
```

### `audit check --full` (Complete)
```
[All of above PLUS:]
  📋 NPC Pipeline State (per NPC: status, weak concepts)
  📦 Dataset Quality (per dataset: row counts, sanitization %)
  🏋️  Training Outputs (runs per NPC, latest checkpoints)
  📊 Evaluation Results (infrastructure status)
```

### `audit diagnose --npc NAME` (Targeted)
```
📋 Current State: [status]
   Weak concepts: [list]
📦 Dataset Status: [row counts]
🏋️  Training Status: [run history]
💡 Recommendations: [next steps]
```

### `audit resume` (Full)
```
[Same as: audit check --full]
```

---

## File Locations

- **Implementation:** `/home/athar/Projects/Unsloth_Core/scripts/audit.py`
- **CLI:** `/home/athar/Projects/Unsloth_Core/ucore`
- **Documentation:** `/home/athar/Projects/Unsloth_Core/.agents/PHASE1_COMPLETION.md`

---

## Integration Points

Audit is integrated with ucore and ready to use. Future phases will:
- Add pre-training auto-checks
- Add post-failure auto-diagnosis
- Add cross-session memory recovery
- Add Supabase historical queries

---

## For Next Session

This audit CLI is now saved in:
- Project memory (searchable via: `memory_search("audit cli implementation")`)
- Skills documentation (view: `skill view unsloth-audit-implementation`)
- Project files (ready to use)

Start any session with: `./ucore audit check --full`
