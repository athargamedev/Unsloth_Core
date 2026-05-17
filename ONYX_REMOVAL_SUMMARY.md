# Summary: Onyx Removal & Reliability Plan

**Created**: 2026-05-17  
**Status**: Ready for Implementation  
**Timeline**: 2 weeks (5 phases)

---

## 📋 What Was Delivered

### 1. **High-Quality Initial Context**
- ✅ Project analysis (2 active NPCs, infrastructure state, recent issues)
- ✅ Persistent memory entries (project state, conventions)
- ✅ Indexed documentation (AGENTS.md, README.md in searchable knowledge base)
- ✅ Context summary document: `.context-summary.md` (quick reference)

### 2. **Comprehensive Improvement Plan**
- ✅ **File**: `/docs/plans/ONYX_REMOVAL_IMPROVEMENT_PLAN.md` (23 KB)
- ✅ Detailed 5-phase roadmap (2 weeks)
- ✅ Current pain points analysis
- ✅ Improvement opportunities (6 major areas)
- ✅ Architecture diagrams (ASCII)
- ✅ Risk mitigation strategies
- ✅ Success criteria for each phase
- ✅ Post-implementation knowledge base structure

### 3. **Detailed Implementation Checklist**
- ✅ **File**: `/docs/plans/PHASE1_IMPLEMENTATION_CHECKLIST.md` (21 KB)
- ✅ Checkboxes for all 5 phases
- ✅ Subtasks with clear deliverables
- ✅ Time estimates per phase
- ✅ Success criteria at each milestone
- ✅ Final completion checklist
- ✅ Clarification questions for you

---

## 🎯 The Plan at a Glance

### **Problem Statement**
- Onyx RAG creates non-deterministic, hard-to-debug dataset generation
- External service dependency (10 Docker containers, network issues)
- Complex failure modes, high maintenance burden
- Tight memory budget on 6GB VRAM
- Difficult to validate or improve dataset quality

### **Solution Strategy**
Replace Onyx with a **deterministic, testable, reliable pipeline**:

| Component | Old (Onyx) | New (Deterministic) |
|-----------|-----------|-------------------|
| **Generation** | RAG + LLM (non-deterministic) | Hash-based templates (reproducible) |
| **Knowledge Source** | Onyx vector DB + reference docs | Knowledge base JSON files |
| **Fallback** | Single point of failure | Chain: deterministic → Ollama → OpenAI |
| **Testing** | Hard to test (black box) | Full unit + integration test suite |
| **Debugging** | Audit trail unclear | Detailed pipeline traces logged |
| **Maintenance** | Onyx setup + indexing | Simple JSON file editing |
| **Reliability** | Cascading failures possible | Circuit breaker + health checks |

---

## 📊 5-Phase Implementation Roadmap

### **Phase 1: Foundation (Week 1)**
- Remove Onyx code completely
- Create `knowledge_base/` directory (replaces Onyx vector DB)
- Implement `generate_deterministic.py` (hash-based reproducibility)
- Update CLI: `--technique deterministic|ollama|openai` (no more Onyx)
- Update NPC specs to use knowledge_base_path

**Deliverable**: First successful `ucore generate` with deterministic output

---

### **Phase 2: Validation & Testing (Week 1.5)**
- Implement comprehensive dataset validator
- Write 30+ unit + integration tests
- Set up CI/CD pipeline (.github/workflows/)
- Target 85%+ code coverage

**Deliverable**: Automated quality gates before training

---

### **Phase 3: Reliability (Week 2)**
- Rewrite feedback loop (no Onyx, deterministic classification)
- Add health checks and circuit breaker pattern
- Implement detailed pipeline tracing
- Add regression detection to evaluation

**Deliverable**: Robust pipeline with clear error messages

---

### **Phase 4: Documentation (Week 2.5)**
- Update all core docs (remove Onyx references)
- Create new docs: deterministic generation, knowledge base curation
- Write migration guide for existing users
- Provide knowledge base examples

**Deliverable**: Clear path for users to upgrade

---

### **Phase 5: Hardening (Week 3)**
- Performance optimization (<1s generation, <5min full pipeline)
- Error recovery & automatic retries
- Security validation + rate limiting
- Final comprehensive testing

**Deliverable**: Production-ready, tested system

---

## ✅ Success Criteria

By end of implementation:
- ✅ Zero Onyx references in codebase
- ✅ Deterministic generation: same input → identical output
- ✅ Generation speed: <1s for 72 examples
- ✅ Validation speed: <2s per dataset
- ✅ Full pipeline: <5 min end-to-end
- ✅ Test coverage: >85% on critical paths
- ✅ 30+ tests, all passing
- ✅ Regression detection working
- ✅ Health checks passing
- ✅ Documentation complete
- ✅ Zero unhandled failures in 10 test runs

---

## 📁 Files Created

### Planning Documents
1. **`/docs/plans/ONYX_REMOVAL_IMPROVEMENT_PLAN.md`** (23 KB)
   - Comprehensive 5-phase roadmap
   - Architecture diagrams
   - Risk mitigation
   - Success criteria

2. **`/docs/plans/PHASE1_IMPLEMENTATION_CHECKLIST.md`** (21 KB)
   - Detailed checklist for all 5 phases
   - Subtasks with clear deliverables
   - Time estimates
   - Clarification questions

3. **`/home/athar/Projects/Unsloth_Core/.context-summary.md`** (12 KB)
   - Quick reference for project state
   - Pipeline overview
   - Current issues
   - Quick-start commands

### Updated Memory
- Saved strategic decision to project memory
- Linked to 5-phase implementation plan
- Documented core changes and success metrics

### Indexed Documentation
- AGENTS.md (indexed in context-mode FTS5)
- README.md (indexed in context-mode FTS5)
- All searchable for future sessions

---

## 🚀 Next Steps (What You Should Do)

### Immediate
1. **Review** the two plan documents:
   - `/docs/plans/ONYX_REMOVAL_IMPROVEMENT_PLAN.md`
   - `/docs/plans/PHASE1_IMPLEMENTATION_CHECKLIST.md`

2. **Answer** clarification questions in the checklist:
   - How should knowledge base content be handled?
   - Validation strictness preference?
   - Test coverage target?
   - etc.

3. **Approve** the plan or request changes

### When Ready to Implement
1. Start with Phase 1 checklist (3 days of work)
2. Focus on removing Onyx code completely
3. Create knowledge_base/ directory structure
4. Implement deterministic generator
5. Test: `ucore generate` works reproducibly

### After Phase 1
- Move to Phase 2 (testing & validation)
- Phases 2-5 follow similar structured approach
- Each phase has clear success criteria

---

## 💡 Key Design Decisions

### 1. **Deterministic Generation**
- Use hash-based seed (`hash(concept:category)`) for reproducible variants
- Templates stored in JSON, not in code
- Rule-based content filling (no LLM calls by default)
- **Benefit**: Git-friendly, testable, debuggable

### 2. **Fallback Chain**
```
deterministic (primary, always works)
    ↓ [if quality issue]
Ollama (local LLM, free)
    ↓ [if Ollama unavailable]
OpenAI (remote LLM, paid)
    ↓ [if all fail]
Manual curation (human expert)
```

### 3. **Knowledge Base (Replaces Onyx)**
```
knowledge_base/
├── category_library.json      (universal templates)
├── prompt_templates.yaml      (2-3 variants per category)
└── domain_concepts/
    ├── history_guide.json     (world history concepts)
    ├── chef_assistant.json    (culinary concepts)
    └── ...
```
- Human-readable JSON (not vector DB black box)
- Can be edited, reviewed, improved
- Version controlled in Git
- Searchable and auditable

### 4. **Comprehensive Testing**
- Unit tests: determinism, distribution, format
- Integration tests: fallback chain, OOM recovery
- CI/CD pipeline: validate every commit
- **Target**: 85%+ coverage on critical paths

### 5. **Reliability Features**
- Circuit breaker: prevent cascading failures
- Health checks: validate before running pipeline
- Pipeline traces: JSONL logs for debugging
- Regression detection: flag performance drops
- Automatic retries: with exponential backoff

---

## 🎓 What This Solves

### Current Problems → Solutions

| Problem | Current | Solution |
|---------|---------|----------|
| Non-deterministic datasets | Onyx RAG varies each run | Hash-based reproducible generation |
| External service dependency | Onyx server + 10 containers | Deterministic generator (no server needed) |
| Hard to debug failures | Black-box RAG retrieval | Detailed pipeline traces logged to JSONL |
| Tight memory budget | 22 Docker containers (Onyx + Supabase) | Deterministic generator uses <50MB |
| No quality validation | Datasets used as-is | Comprehensive validation gates |
| No error recovery | One failure = pipeline breaks | Circuit breakers + automatic retries |
| Poor testing | Difficult to test generation | 30+ unit + integration tests |
| Unclear feedback loop | Onyx determines regeneration | Transparent classification (training_density vs quality vs missing) |

---

## 💼 Business Value

### For You
- ✅ Simplified maintenance (no Onyx setup)
- ✅ Reproducible results (easier to share, compare)
- ✅ Faster debugging (clear traces, testable components)
- ✅ Higher reliability (circuit breakers, health checks)
- ✅ Better documentation (clear migration path)
- ✅ Portable (works on any machine, no external services)

### For Future Team Members
- ✅ Easier onboarding (no Onyx complexity)
- ✅ Clear architecture (deterministic generation is understandable)
- ✅ Good test coverage (confidence in changes)
- ✅ Comprehensive logging (easy to debug)
- ✅ Documented knowledge bases (can improve without code changes)

---

## ⏱️ Time Estimate

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| Phase 1: Foundation | 3 days | Onyx removed, deterministic generation working |
| Phase 2: Testing | 2 days | 30+ tests, CI/CD pipeline |
| Phase 3: Reliability | 2 days | Health checks, circuit breaker, traces |
| Phase 4: Documentation | 1.5 days | Updated docs, migration guide |
| Phase 5: Hardening | 1.5 days | Performance optimization, final testing |
| **Total** | **~2 weeks** | Production-ready system |

---

## 📞 Support During Implementation

If you start implementing and have questions:
1. Check the detailed checklist in `/docs/plans/PHASE1_IMPLEMENTATION_CHECKLIST.md`
2. Review the main plan: `/docs/plans/ONYX_REMOVAL_IMPROVEMENT_PLAN.md`
3. Refer to `.context-summary.md` for quick facts

All documents are stored in the repo for reference.

---

## 🎉 Final Note

This plan transforms Unsloth_Core from a complex system with Onyx dependencies into a **simple, testable, maintainable project** that's easier to debug, deploy, and improve over time.

The deterministic approach aligns better with:
- ML best practices (reproducibility)
- Software engineering best practices (testing, logging, monitoring)
- Your hardware constraints (6GB VRAM)
- Your team's needs (debugging, maintenance)

**All planning is complete. Ready to implement when you give the go-ahead.**

---

**Questions?** Review the documents above or ask clarification questions in the checklist.

**Ready to start?** Let me know and I'll begin Phase 1 implementation.
