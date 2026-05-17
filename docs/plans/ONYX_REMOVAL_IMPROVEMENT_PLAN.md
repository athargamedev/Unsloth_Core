# Unsloth_Core Reliability & Improvement Plan (Onyx Removal + Architecture Hardening)

## Executive Summary

**Decision**: Remove Onyx RAG completely. Replace with deterministic, testable dataset generation pipeline with multiple fallback techniques.

**Goal**: Make the project **reliable, debuggable, and maintainable** by:
1. Eliminating external service dependencies (Onyx servers, network failures)
2. Creating deterministic, reproducible dataset generation
3. Building robust fallback mechanisms
4. Implementing comprehensive testing and validation
5. Simplifying the pipeline to reduce failure points

**Timeline**: 2-3 weeks for full implementation and validation

---

## 📊 Current Pain Points Analysis

### Onyx Issues (Inferred)
| Issue | Severity | Impact | Root Cause |
|-------|----------|--------|-----------|
| **External service dependency** | 🔴 High | Pipeline breaks if Onyx server down | Requires separate Docker container + network reliability |
| **Non-deterministic generation** | 🔴 High | Different datasets each run, hard to debug | RAG retrieval order + LLM sampling variance |
| **Complex failure modes** | 🔴 High | Hard to diagnose failures | Network + indexing + retrieval + template rendering |
| **Memory overhead** | 🟡 Medium | Tight budget on 6GB VRAM (Onyx 10 containers) | Vector DB + embeddings services |
| **Debugging difficulty** | 🟡 Medium | Can't easily inspect what Onyx retrieved | Black-box retrieval, no audit trail |
| **Documentation drift** | 🟡 Medium | Primer files don't always match generation | Manual sync between reference_docs + generation |

### Current System Weaknesses
| Component | Weakness | Impact |
|-----------|----------|--------|
| **Dataset Generation** | Multi-step (spec → templates → Onyx → filtering) | Multiple failure points |
| **Evaluation** | No automated regression detection | Performance regressions go unnoticed |
| **Training** | OOM crashes with concurrent services | 6GB VRAM pressure |
| **Error Handling** | Sparse logging, unclear failure reasons | Time-consuming debugging |
| **Testing** | Minimal unit tests for critical paths | Bugs slip through |
| **Monitoring** | No alerts or health checks | Issues discovered late |

---

## 🎯 Improvement Opportunities

### 1. **Deterministic Dataset Generation**

**Current**: Template-based (deterministic but thin) + Onyx (non-deterministic, complex)

**New Architecture**:
```
Subject Spec JSON
    ↓
Knowledge Base (structured, versioned)
    ├─ category_library.json (identity traits, teaching concepts, dialogue patterns)
    ├─ domain_concepts.json (curated by domain experts)
    └─ prompt_templates.yaml (with variants)
    ↓
Deterministic Generator
    ├─ Seed: hash(concept + category + variant_index)
    ├─ Template selection: fixed, reproducible
    ├─ Content filling: rule-based (not LLM)
    ├─ Variant picking: _pick_variant(seed) → fixed
    └─ Output: train.jsonl (100% reproducible given same seed)
    ↓
Quality Metrics (automated, per-dataset)
    ├─ Diversity score (lexical + semantic)
    ├─ Coverage check (all concepts present)
    ├─ Format validation (ChatML compliance)
    └─ Concept balance check (8/32/16/8/8 distribution)
```

**Benefits**:
- ✅ Same input → same output always
- ✅ Git-friendly (datasets become reproducible artifacts)
- ✅ Easy to test and debug
- ✅ No network dependencies
- ✅ Fast (sub-second generation)
- ✅ Audit trail: trace any example back to source

**Fallback Chain**:
1. **Primary**: Deterministic template + knowledge base
2. **Secondary**: LLM-grounded (Ollama/OpenAI) for enrichment when needed
3. **Tertiary**: Domain expert reviews + manual curation for hard concepts

---

### 2. **Robust Multi-Technique Pipeline**

Replace `--technique onyx` with a **priority-based fallback system**:

```
./ucore generate subjects/history_guide.json --technique deterministic [default]
./ucore generate subjects/history_guide.json --technique ollama [fallback 1]
./ucore generate subjects/history_guide.json --technique openai [fallback 2]
./ucore generate subjects/history_guide.json --technique manual [human curation]
```

**Execution Strategy**:
```python
def generate_dataset(spec, technique='deterministic', fallback=True):
    try:
        if technique == 'deterministic':
            return _generate_deterministic(spec)
    except Exception as e:
        log_error(f"Deterministic generation failed: {e}")
        if fallback and technique != 'deterministic':
            raise  # don't double-fallback
        
        # Fallback 1: Ollama (local LLM)
        try:
            log_info("Attempting Ollama fallback...")
            return _generate_ollama(spec)
        except Exception as e:
            log_error(f"Ollama fallback failed: {e}")
        
        # Fallback 2: OpenAI (if key available)
        try:
            log_info("Attempting OpenAI fallback...")
            return _generate_openai(spec)
        except Exception as e:
            log_error(f"OpenAI fallback failed: {e}")
        
        # Fallback 3: Manual (stub)
        raise GenerationFailedError(
            f"All generation techniques failed. "
            f"Generate manually: python scripts/manual_curator.py {spec}"
        )
```

---

### 3. **Comprehensive Data Validation Layer**

Add **automatic quality gates** before training:

```python
# scripts/validate_dataset.py
class DatasetValidator:
    def __init__(self, jsonl_path, spec_path):
        self.data = load_jsonl(jsonl_path)
        self.spec = load_json(spec_path)
    
    def validate_all(self):
        """Run all checks, return structured report."""
        report = {
            'passed': [],
            'warnings': [],
            'errors': [],
            'metrics': {}
        }
        
        # Format validation
        report.update(self._validate_chatml_format())
        
        # Distribution validation
        report.update(self._validate_category_distribution())
        
        # Content validation
        report.update(self._validate_content_quality())
        
        # Coverage validation
        report.update(self._validate_concept_coverage())
        
        # Diversity metrics
        report['metrics'] = self._compute_diversity()
        
        return report
```

**Validation Checks**:
- ✅ ChatML format compliance (role, content fields)
- ✅ Category distribution (8/32/16/8/8 ± 10%)
- ✅ No duplicates (exact + semantic)
- ✅ Concept coverage (all teaching expertise covered)
- ✅ Diversity metrics (TTR, Simpsons diversity)
- ✅ Token count estimates (fit in context window)
- ✅ Refusal examples present (safety guardrails)

**Pre-Training Gate**:
```bash
./ucore validate subjects/datasets/history_guide/deterministic/train.jsonl \
  --spec subjects/history_guide.json \
  --strict  # Fail if any error
```

---

### 4. **Automated Testing & Regression Detection**

**Unit Tests** (new):
```python
# tests/test_dataset_generation.py
def test_deterministic_generation_reproducibility():
    """Same seed + spec = same dataset always"""
    spec = load_json("subjects/history_guide.json")
    data1 = generate_deterministic(spec, seed=42)
    data2 = generate_deterministic(spec, seed=42)
    assert data1 == data2  # byte-for-byte identical

def test_dataset_meets_distribution():
    """Generated dataset respects category distribution"""
    data = generate_deterministic(spec)
    categories = [ex['metadata']['category'] for ex in data]
    assert Counter(categories) == {'identity': 8, 'teaching': 32, ...}

def test_validation_gates_catch_bad_data():
    """Validator rejects malformed datasets"""
    bad_data = [{'no_role_field': "..."}]  # Missing ChatML
    report = validate(bad_data)
    assert len(report['errors']) > 0

def test_training_pipeline_end_to_end():
    """Full pipeline: generate → validate → train → export"""
    # Generate
    dataset = generate_deterministic(spec)
    # Validate
    report = validate(dataset, spec)
    assert report['passed']
    # Train (smoke test, small epochs)
    model = train_model(dataset, epochs=1, preset='smoke')
    # Export
    gguf = export_to_gguf(model)
    assert gguf.exists()

def test_eval_regression_detection():
    """Eval compares new model vs baseline, flags regressions"""
    baseline_metrics = {'win_rate': 0.60, 'avg_quality': 0.78}
    candidate_metrics = {'win_rate': 0.45, 'avg_quality': 0.71}
    report = compare_eval(baseline_metrics, candidate_metrics)
    assert len(report['regressions']) > 0
```

**Integration Tests** (new):
```python
# tests/test_pipeline_resilience.py
def test_pipeline_survives_ollama_down():
    """Generation falls back to deterministic if Ollama unavailable"""
    stop_ollama()
    try:
        data = generate(spec, technique='ollama', fallback=True)
        # Should fall back to deterministic, not crash
        assert len(data) > 0
    finally:
        start_ollama()

def test_dataset_validation_on_all_npcs():
    """Every active NPC dataset passes validation"""
    for npc_spec in load_all_specs():
        dataset_path = get_dataset_path(npc_spec)
        report = validate(dataset_path, npc_spec)
        assert all(report['passed']), f"{npc_spec} failed: {report}"

def test_training_osx_memory_safety():
    """Training doesn't crash with concurrent Supabase + Onyx containers"""
    # Start all services
    start_supabase()
    start_onyx()  # Even though we're removing it, test the boundary
    try:
        train_model(spec, preset='safe-any')  # Use memory-safe preset
        assert training_completed()
    finally:
        stop_all_services()
```

---

### 5. **Simplified Feedback Loop (No Onyx)**

**Old (with Onyx)**:
```
Eval Results → Query Onyx for concept docs → Determine gap type → Regenerate with Onyx
```

**New (deterministic)**:
```
Eval Results
    ↓
Weak Concepts Detected (win_rate < 0.5)
    ↓
Classification:
    ├─ training_density: Increase example count (existing templates, more variants)
    ├─ quality_issue: Improve prompt templates / knowledge base
    └─ concept_missing: Add to domain_concepts.json (manual expert review)
    ↓
Regenerate with:
    ├─ --concept-focus [weak_concepts]  # Boost variant count for weak areas
    ├─ --seed [increment]               # Deterministic new examples
    └─ --enrichment [ollama|openai]     # Optional LLM polish
    ↓
Retrain + Re-evaluate
```

**Advantages**:
- No Onyx dependency
- Transparent: see exactly why a concept is weak
- Actionable: human can review and improve templates
- Deterministic: results reproducible

---

### 6. **Pipeline Reliability Features**

#### 6a. Comprehensive Logging & Debugging
```python
# _config/log_setup.py (enhanced)
def log_state(stage, npc_key, state_dict, checkpoint=False):
    """Log state transitions with full context."""
    timestamp = datetime.utcnow().isoformat()
    log_entry = {
        'timestamp': timestamp,
        'stage': stage,
        'npc_key': npc_key,
        'state': state_dict,
        'checkpoint': checkpoint,
    }
    # Write to JSON log for machine parsing
    write_to_jsonl(f"logs/pipeline_trace_{npc_key}.jsonl", log_entry)
    # Also print human-readable version
    log_info(json.dumps(log_entry, indent=2))

# Usage in pipeline
log_state('generation', 'history_guide', {
    'technique': 'deterministic',
    'seed': 42,
    'example_count': 72,
    'categories': {'identity': 8, 'teaching': 32, ...}
}, checkpoint=True)
```

#### 6b. Circuit Breaker Pattern
```python
# Prevent cascading failures
class CircuitBreaker:
    def __init__(self, failure_threshold=3, timeout=300):
        self.failures = 0
        self.threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
    
    def call(self, func, *args, **kwargs):
        """Execute func with circuit breaker protection."""
        if self.is_open():
            raise CircuitBreakerOpen(
                f"Circuit open. Too many failures. Wait {self.timeout}s."
            )
        try:
            result = func(*args, **kwargs)
            self.reset()
            return result
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.threshold:
                log_error(f"Circuit breaker triggered after {self.failures} failures")
            raise

# Usage
breaker = CircuitBreaker(failure_threshold=3)
try:
    data = breaker.call(generate, spec)
except CircuitBreakerOpen:
    log_error("Generation circuit open, waiting for recovery...")
    # Fall back to cached dataset or manual intervention
```

#### 6c. Health Checks & Monitoring
```python
# scripts/health_check.py (enhanced)
def health_check(verbose=False):
    """Check all systems, return JSON report."""
    checks = {
        'timestamp': datetime.utcnow().isoformat(),
        'environment': {
            'python_version': sys.version,
            'venv_active': is_venv_active(),
            'project_root': PROJECT_ROOT,
        },
        'disk': check_disk_space(),
        'gpu': check_gpu_memory(),
        'services': {
            'docker': check_docker(),
            'supabase': check_supabase(),
            'ollama': check_ollama(),  # Optional
        },
        'data_integrity': {
            'specs_valid': validate_all_specs(),
            'datasets_valid': validate_all_datasets(),
            'exports_present': check_exports(),
        },
        'recent_errors': load_recent_errors(),
    }
    return checks
```

---

## 🔧 Implementation Roadmap

### Phase 1: Foundation (Week 1)
**Goal**: Remove Onyx, establish deterministic generation

- [ ] **1.1** Create `knowledge_base/` directory structure:
  - `category_library.json` (identity traits, dialogue patterns, teaching concepts)
  - `domain_concepts/{npc_key}.json` (per-NPC curated knowledge)
  - `prompt_templates.yaml` (templates with variants)

- [ ] **1.2** Implement deterministic generator:
  - `scripts/generate_deterministic.py`
  - Hash-based variant selection (_pick_variant)
  - Rule-based content filling (no LLM calls)
  - Output: identical results for same seed + spec

- [ ] **1.3** Update `generate_dataset.py`:
  - Add `--technique deterministic` (new default)
  - Keep `--technique ollama/openai` (fallbacks)
  - Remove `--technique onyx` option
  - Add fallback chain logic

- [ ] **1.4** Update NPC specs:
  - Add `knowledge_base_path` field
  - Add `deterministic_generation_config` section
  - Migrate reference_docs → knowledge_base/

- [ ] **1.5** Remove Onyx references:
  - Delete unused scripts: `onyx_client.py`, `onyx_index_repo.py`, etc.
  - Update docs: remove Onyx setup instructions
  - Update AGENTS.md to reflect new workflow

**Deliverables**:
- Deterministic generator passes basic tests
- `ucore generate` defaults to `--technique deterministic`
- Fallback chain works (Ollama tested)
- Git-clean removal of Onyx code

---

### Phase 2: Validation & Testing (Week 1.5)
**Goal**: Comprehensive testing for data quality and reliability

- [ ] **2.1** Implement dataset validator:
  - `scripts/validate_dataset.py`
  - Format, distribution, diversity, coverage checks
  - Generate HTML/JSON validation reports

- [ ] **2.2** Add unit tests:
  - `tests/test_dataset_generation.py`
  - `tests/test_validation.py`
  - Reproducibility tests
  - Distribution tests
  - Format compliance tests

- [ ] **2.3** Add integration tests:
  - `tests/test_pipeline_resilience.py`
  - End-to-end pipeline tests
  - Fallback mechanism tests
  - Memory safety tests

- [ ] **2.4** CI/CD pipeline:
  - GitHub Actions workflow
  - Run tests on every commit
  - Check dataset validity for every NPC

**Deliverables**:
- 30+ unit + integration tests
- Validation gate before training: `ucore validate`
- Test coverage report (target: 85%+ on critical paths)
- CI workflow for continuous validation

---

### Phase 3: Feedback Loop & Reliability (Week 2)
**Goal**: Non-Onyx feedback loop, health monitoring

- [ ] **3.1** Rewrite feedback loop (no Onyx):
  - `scripts/feedback_loop_v2.py`
  - Weak concept detection (deterministic)
  - Gap classification (template vs LLM enrichment)
  - Regeneration with `--concept-focus`

- [ ] **3.2** Add health checks:
  - `scripts/health_check.py` (comprehensive)
  - `./ucore health` CLI command
  - JSON output for monitoring

- [ ] **3.3** Implement circuit breaker pattern:
  - Prevent cascading failures
  - Graceful degradation
  - Timeout recovery

- [ ] **3.4** Enhanced logging:
  - Pipeline trace logging (JSONL format)
  - Per-stage state checkpoints
  - Error categorization & suggestions

- [ ] **3.5** Update evaluation:
  - Add regression detection
  - Compare to baseline automatically
  - Flag significant drops in metrics

**Deliverables**:
- Feedback loop works without Onyx
- Health checks pass on every run
- Detailed pipeline traces for debugging
- Regression detection built-in

---

### Phase 4: Documentation & Handoff (Week 2.5)
**Goal**: Updated docs, clear migration path for users

- [ ] **4.1** Update documentation:
  - `docs/TRAINING_WORKFLOW_CONTEXT.md` (remove Onyx)
  - `docs/DETERMINISTIC_GENERATION.md` (new, detailed)
  - `docs/KNOWLEDGE_BASE_CURATION.md` (new, for domain experts)
  - Update AGENTS.md with new workflow
  - Update README.md

- [ ] **4.2** Create migration guide:
  - `ONYX_REMOVAL_MIGRATION.md`
  - How to upgrade existing projects
  - How to regenerate datasets with new technique
  - Troubleshooting common issues

- [ ] **4.3** Update CLI help:
  - `ucore generate --help` reflects new options
  - Clear warnings if old `--technique onyx` used
  - Helpful error messages

- [ ] **4.4** Create example knowledge bases:
  - `knowledge_base/examples/` directory
  - Example for history_guide
  - Example for chef_assistant
  - Template for new NPCs

**Deliverables**:
- Comprehensive updated docs
- Migration guide for existing projects
- Clear examples for new NPCs
- Helpful CLI error messages

---

### Phase 5: Hardening & Optimization (Week 3)
**Goal**: Make the system rock-solid and performant

- [ ] **5.1** Performance optimization:
  - Benchmark deterministic generation (target: <1s)
  - Cache validation results
  - Optimize JSONL I/O

- [ ] **5.2** Error recovery:
  - Partial dataset recovery on failure
  - Automatic retry with backoff
  - Detailed error suggestions

- [ ] **5.3** Add telemetry (opt-in):
  - Track generation time, data quality metrics
  - Send to W&B for analysis
  - Identify slow/problem areas

- [ ] **5.4** Security hardening:
  - Validate all input JSON
  - Sanitize LLM outputs when used
  - Rate limit external API calls

- [ ] **5.5** Final testing pass:
  - Full end-to-end pipeline tests (all NPCs)
  - Stress tests (large datasets, concurrent operations)
  - Recovery tests (failure scenarios)

**Deliverables**:
- Deterministic generation: <1s
- Validation: <2s per dataset
- Full pipeline: <5 min (including training)
- Zero regressions from Onyx removal

---

## 📋 Success Criteria

### By End of Phase 1
- ✅ Onyx code completely removed from repo
- ✅ `ucore generate --technique deterministic` works for all NPCs
- ✅ Generated datasets identical for same seed
- ✅ Fallback chain functional (Ollama tested)

### By End of Phase 2
- ✅ 30+ unit + integration tests passing
- ✅ Dataset validator catches all common errors
- ✅ CI/CD pipeline validates every commit
- ✅ Test coverage >85% on critical paths

### By End of Phase 3
- ✅ Feedback loop works without Onyx
- ✅ Health checks pass daily
- ✅ Pipeline traces enable easy debugging
- ✅ Regression detection alerts on metric drops

### By End of Phase 4
- ✅ All documentation updated
- ✅ Migration guide clear and tested
- ✅ New NPCs can be created in <30 min
- ✅ User feedback incorporated

### By End of Phase 5
- ✅ Full pipeline <5 min end-to-end
- ✅ Zero unhandled failures in 10 test runs
- ✅ Recovery from all common failure scenarios
- ✅ Project deemed "production-ready"

---

## 🎓 Knowledge Base Structure (Post-Onyx)

```
Unsloth_Core/
├── knowledge_base/                      [NEW] Replaces Onyx
│   ├── category_library.json            # Universal traits, patterns
│   ├── prompt_templates.yaml            # Base templates with variants
│   ├── domain_concepts/
│   │   ├── history_guide.json           # World history concepts
│   │   ├── chef_assistant.json          # Culinary concepts
│   │   └── ...
│   └── README.md                        # How to maintain knowledge base
│
├── subjects/                            [MIGRATED]
│   ├── history_guide.json               # Remove Onyx refs
│   ├── chef_assistant.json              # Add knowledge_base_path
│   └── reference_docs/                  [DEPRECATED - archive]
│       └── (old primer files)
│
├── scripts/
│   ├── generate_deterministic.py        [NEW]
│   ├── generate_dataset.py              [UPDATED - Onyx removed]
│   ├── validate_dataset.py              [NEW]
│   ├── health_check.py                  [UPDATED]
│   ├── feedback_loop_v2.py              [NEW - No Onyx]
│   ├── onyx_*.py                        [DELETED]
│   └── ...
│
├── tests/                               [EXPANDED]
│   ├── test_dataset_generation.py       [NEW]
│   ├── test_validation.py               [NEW]
│   ├── test_pipeline_resilience.py      [NEW]
│   ├── test_feedback_loop.py            [NEW]
│   └── ...
│
├── .github/workflows/
│   ├── test.yml                         [NEW - CI pipeline]
│   └── ...
│
├── docs/
│   ├── TRAINING_WORKFLOW_CONTEXT.md     [UPDATED]
│   ├── DETERMINISTIC_GENERATION.md      [NEW]
│   ├── KNOWLEDGE_BASE_CURATION.md       [NEW]
│   ├── ONYX_REMOVAL_MIGRATION.md        [NEW]
│   └── ...
└── AGENTS.md                            [UPDATED]
```

---

## 🚨 Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Generated data quality drops | Medium | High | Extensive validation, domain expert review in Phase 4 |
| Existing users lose functionality | Low | High | Clear migration guide, backward compat testing |
| Performance regression | Low | Medium | Benchmarking in Phase 5, optimization pass |
| Incomplete Onyx removal | Low | Medium | Comprehensive grep + code review |
| Test suite false negatives | Medium | Medium | Multiple testing strategies, real-world runs |

---

## 🎯 Next Steps

1. **Review & Approve** this plan (1 day)
2. **Phase 1 Implementation** (3 days)
3. **Phase 2 Testing** (2 days)
4. **Phase 3 Feedback & Monitoring** (2 days)
5. **Phase 4 Documentation** (1.5 days)
6. **Phase 5 Hardening** (1.5 days)
7. **Full Validation & Handoff** (1 day)

**Total Effort**: ~12-14 days / 2 weeks

---

## 📞 Questions & Clarifications Needed

1. **Knowledge Base Content**: Should I auto-generate initial knowledge bases from current reference_docs, or do you want to review/improve them first?
2. **Validation Strictness**: Should `ucore validate --strict` block training if diversity metrics are below threshold, or just warn?
3. **Fallback Strategy**: If deterministic generation is default, should `--technique ollama` be explicit or automatic if available?
4. **Domain Expert Reviews**: Do you plan to manually curate knowledge bases per NPC, or keep them templated?
5. **Testing Coverage**: Is 85% unit test coverage sufficient, or target higher?

---

**Document Created**: 2026-05-17  
**Status**: Ready for Review & Approval  
**Next Step**: Approve plan and begin Phase 1 implementation
