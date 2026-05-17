# ONYX REMOVAL IMPLEMENTATION CHECKLIST

**Status**: Ready to Begin Phase 1  
**Timeline**: 2 weeks (5 phases)  
**Created**: 2026-05-17  

---

## ✅ Phase 1: Foundation (Week 1)
**Goal**: Remove Onyx, establish deterministic generation, set up fallback chain

### 1.1 Create Knowledge Base Structure
- [ ] Create `knowledge_base/` directory at project root
- [ ] Create `knowledge_base/category_library.json` with universal traits/patterns
  - Identity traits (5-10 examples per NPC type)
  - Teaching patterns (explanation templates, misconception corrections)
  - Dialogue patterns (natural conversation variations)
  - Quest scenarios (challenge types)
  - Refusal patterns (safe boundary responses)
- [ ] Create `knowledge_base/prompt_templates.yaml` with base templates + 2-3 variants per category
- [ ] Create `knowledge_base/domain_concepts/` directory
- [ ] Migrate `subjects/reference_docs/history_primer.md` → `knowledge_base/domain_concepts/history_guide.json`
- [ ] Migrate `subjects/reference_docs/chef_primer.md` → `knowledge_base/domain_concepts/chef_assistant.json`
- [ ] Create `knowledge_base/README.md` with maintenance guide

### 1.2 Implement Deterministic Generator
- [ ] Create `scripts/generate_deterministic.py`
  - [ ] Function: `_pick_variant(seed, category, variant_count)` (hash-based)
  - [ ] Function: `_fill_template(template, concept, variant_index, knowledge_base)`
  - [ ] Function: `generate_deterministic(spec, knowledge_base, seed=42)`
  - [ ] Ensure: same seed + spec = identical output always
  - [ ] Output: ChatML JSONL with metadata (concept, category, variant_seed)
- [ ] Test: reproducibility test (run twice, compare hashes)
- [ ] Test: distribution test (verify 8/32/16/8/8 split)

### 1.3 Update Dataset Generation CLI
- [ ] Modify `scripts/generate_dataset.py`:
  - [ ] Remove all Onyx references
  - [ ] Add `--technique deterministic` (new default)
  - [ ] Keep `--technique ollama` (fallback 1)
  - [ ] Keep `--technique openai` (fallback 2)
  - [ ] Remove `--technique onyx` option
  - [ ] Add fallback chain logic with detailed error reporting
- [ ] Update `ucore` CLI:
  - [ ] Update generate subcommand: `--technique` choices = [deterministic, ollama, openai, template]
  - [ ] Update help text (remove Onyx references)
  - [ ] Test: `ucore generate subjects/history_guide.json --technique deterministic` works

### 1.4 Update NPC Specs
- [ ] Modify `subjects/history_guide.json`:
  - [ ] Add field: `"knowledge_base_path": "knowledge_base/domain_concepts/history_guide.json"`
  - [ ] Remove field: `"reference_doc"` (if exists)
  - [ ] Add section: `"deterministic_generation_config": {variants_per_category: {teaching: 3, ...}}`
- [ ] Modify `subjects/chef_assistant.json` (same changes)
- [ ] Validate: both specs pass `ucore validate-config`

### 1.5 Remove Onyx Code & References
- [ ] Delete scripts:
  - [ ] `scripts/onyx_client.py`
  - [ ] `scripts/onyx_index_repo.py`
  - [ ] `scripts/onyx_supabase_sync.py`
  - [ ] Any other `onyx_*.py` files
- [ ] Update docs:
  - [ ] `docs/TRAINING_WORKFLOW_CONTEXT.md`: remove Onyx sections
  - [ ] `docs/ONYX_WORKFLOW.md`: archive or delete
  - [ ] `AGENTS.md`: remove Onyx references
- [ ] Update code references:
  - [ ] `grep -r "onyx\|Onyx" --include="*.py"` in scripts/ → ensure results are only in removed files or comments
  - [ ] `grep -r "onyx\|Onyx" --include="*.md"` in docs/ → remove/archive all
- [ ] Git clean:
  - [ ] Commit: "refactor: remove Onyx integration completely"
  - [ ] Verify: all Onyx code deleted

### 1.6 Test Phase 1
- [ ] Test: `ucore generate subjects/history_guide.json` (defaults to deterministic)
- [ ] Test: run twice, verify identical outputs (byte-for-byte)
- [ ] Test: `ucore generate subjects/history_guide.json --technique ollama` (if Ollama available)
- [ ] Test: datasets generated in `subjects/datasets/history_guide/deterministic/train.jsonl`
- [ ] Manual: verify dataset has 72 examples, correct ChatML format

**Phase 1 Success Criteria**:
- ✅ Onyx code completely removed from repo
- ✅ Deterministic generator produces reproducible datasets
- ✅ Fallback chain functional (Ollama tested)
- ✅ All 3 commands work: `ucore generate --technique [deterministic|ollama|openai]`

**Time Estimate**: 3 days

---

## ✅ Phase 2: Validation & Testing (Week 1.5)
**Goal**: Comprehensive testing for data quality and pipeline reliability

### 2.1 Implement Dataset Validator
- [ ] Create `scripts/validate_dataset.py`
  - [ ] Function: `validate_chatml_format(jsonl_data)` - check role/content fields
  - [ ] Function: `validate_category_distribution(data, spec)` - check 8/32/16/8/8 ± 10%
  - [ ] Function: `validate_no_duplicates(data)` - detect exact + semantic duplicates
  - [ ] Function: `validate_concept_coverage(data, spec)` - ensure all teaching.expertise covered
  - [ ] Function: `compute_diversity_metrics(data)` - TTR, Simpsons diversity
  - [ ] Function: `validate_token_counts(data, model)` - fit in context window
  - [ ] Function: `validate_all(jsonl_path, spec_path)` - returns structured report (JSON)
- [ ] Create CLI: `ucore validate <jsonl> --spec <spec.json> [--strict]`
  - [ ] Output: JSON report with passed/warnings/errors/metrics
  - [ ] Strict mode: fail on any error, not just warnings
  - [ ] Non-strict: only warn, allow training to proceed

### 2.2 Add Unit Tests
- [ ] Create `tests/test_dataset_generation.py`:
  - [ ] test_deterministic_reproducibility()
  - [ ] test_deterministic_distribution()
  - [ ] test_deterministic_chatml_format()
  - [ ] test_concept_extraction_from_spec()
  - [ ] test_variant_selection_consistency()
- [ ] Create `tests/test_validation.py`:
  - [ ] test_chatml_format_validation()
  - [ ] test_distribution_validation()
  - [ ] test_duplicate_detection()
  - [ ] test_concept_coverage()
  - [ ] test_diversity_metrics()
  - [ ] test_validator_catches_malformed_data()
- [ ] Create `tests/test_dataset_fixtures.py`:
  - [ ] Fixture: valid dataset (72 examples, correct distribution)
  - [ ] Fixture: invalid dataset (missing fields)
  - [ ] Fixture: underdistributed dataset (not 8/32/16/8/8)
- [ ] Run tests: `pytest tests/ -v` → all green

### 2.3 Add Integration Tests
- [ ] Create `tests/test_pipeline_resilience.py`:
  - [ ] test_generation_fallback_chain() - all techniques attempted
  - [ ] test_generation_without_ollama() - works if Ollama down
  - [ ] test_generation_without_openai() - works if API key missing
  - [ ] test_validation_on_all_npcs() - every NPC dataset passes
  - [ ] test_training_with_generated_data() - full pipeline smoke test
  - [ ] test_export_after_training() - GGUF generated successfully

### 2.4 Set Up CI/CD Pipeline
- [ ] Create `.github/workflows/test.yml`:
  - [ ] Trigger: push to main, PRs
  - [ ] Steps:
    - [ ] Activate venv
    - [ ] Run unit tests: `pytest tests/test_*.py -v`
    - [ ] Run integration tests: `pytest tests/test_pipeline_*.py -v`
    - [ ] Check code coverage: `pytest --cov=scripts tests/ --cov-report=html`
    - [ ] Report: coverage badge added to README
- [ ] Create `.github/workflows/validate_datasets.yml`:
  - [ ] Trigger: any commit modifying subjects/
  - [ ] Steps:
    - [ ] Validate all active NPC datasets
    - [ ] Report: pass/fail for each NPC
    - [ ] Fail PR if validation errors

### 2.5 Test Phase 2
- [ ] Run all tests locally: `pytest tests/ -v --cov=scripts`
- [ ] Target: 85%+ code coverage on critical paths
- [ ] Manual: validate dataset for history_guide and chef_assistant
- [ ] Manual: verify CI workflow triggers on commit

**Phase 2 Success Criteria**:
- ✅ 30+ unit + integration tests passing
- ✅ Validator catches all common data errors
- ✅ CI/CD pipeline validates every commit
- ✅ Test coverage >85% on critical paths

**Time Estimate**: 2 days

---

## ✅ Phase 3: Feedback Loop & Reliability (Week 2)
**Goal**: Non-Onyx feedback loop, health monitoring, robust error handling

### 3.1 Rewrite Feedback Loop (No Onyx)
- [ ] Create `scripts/feedback_loop_v2.py`:
  - [ ] Function: `detect_weak_concepts(eval_json)` - concepts with win_rate < 0.5
  - [ ] Function: `classify_gap(weak_concepts, knowledge_base)`:
    - [ ] training_density: concept in knowledge_base but few examples
    - [ ] quality_issue: concept in knowledge_base but templates need improvement
    - [ ] concept_missing: concept not in knowledge_base (needs expert review)
  - [ ] Function: `regenerate_focused(spec, weak_concepts, knowledge_base)`:
    - [ ] --concept-focus [weak_concepts]
    - [ ] --seed [increment for determinism]
    - [ ] --enrichment [ollama|openai] for quality improvement
  - [ ] Function: `generate_report()` - structured output (JSON + markdown)
- [ ] Update `ucore` CLI:
  - [ ] Add command: `ucore feedback <eval_json> --dry-run [--auto]`
  - [ ] `--dry-run`: show what would be regenerated, don't execute
  - [ ] `--auto`: actually regenerate weak-concept datasets

### 3.2 Add Health Checks
- [ ] Create/enhance `scripts/health_check.py`:
  - [ ] Check: Python version, venv active
  - [ ] Check: Disk space (critical if <1GB)
  - [ ] Check: GPU memory available
  - [ ] Check: Docker running, sufficient allocation
  - [ ] Check: Supabase services healthy (optional)
  - [ ] Check: All NPC specs valid
  - [ ] Check: All datasets valid
  - [ ] Check: GGUF exports present
  - [ ] Check: Recent errors/failures
  - [ ] Output: JSON report with health score (0-100)
- [ ] Update `ucore` CLI:
  - [ ] Add command: `ucore health [--verbose]`
  - [ ] Default: concise report, traffic-light status
  - [ ] Verbose: detailed breakdown per check
- [ ] Integration:
  - [ ] Run `./ucore health` at start of every pipeline run
  - [ ] Fail fast if critical issues (disk space, GPU memory)

### 3.3 Implement Circuit Breaker Pattern
- [ ] Create `scripts/circuit_breaker.py`:
  - [ ] Class: `CircuitBreaker(failure_threshold, timeout_seconds)`
  - [ ] Methods: `call(func, *args)`, `reset()`, `is_open()`
  - [ ] Behavior: track failures, open after threshold, auto-recover after timeout
- [ ] Apply to generation:
  - [ ] Wrap: `generate_deterministic()`, `generate_ollama()`, `generate_openai()`
  - [ ] Effect: prevent cascading failures if technique unavailable
- [ ] Apply to export/eval:
  - [ ] Wrap: llama-server startup, GGUF conversion
  - [ ] Effect: graceful degradation instead of hard crashes

### 3.4 Enhanced Logging
- [ ] Create `scripts/pipeline_trace.py`:
  - [ ] Function: `log_state(stage, npc_key, state_dict, checkpoint=False)`
  - [ ] Output: JSONL file `logs/pipeline_trace_{npc_key}.jsonl`
  - [ ] Checkpoint: save full state at critical milestones (generation done, training done, export done)
  - [ ] Includes: timestamp, stage name, state dict, error (if any)
- [ ] Integration:
  - [ ] Call at start of each stage (generate, sanitize, train, export, eval)
  - [ ] Call at end of each stage (success or failure)
  - [ ] Call on error with full traceback
- [ ] Output: human-readable trace + JSON for analysis

### 3.5 Regression Detection in Evaluation
- [ ] Update `scripts/evaluate.py`:
  - [ ] Add function: `compare_to_baseline(candidate_metrics, baseline_metrics)`
  - [ ] Detect: win_rate drop >10%, quality drop >5%, violations increase
  - [ ] Flag: as "REGRESSION" in report if detected
  - [ ] Recommend: investigate or rollback
  - [ ] Integration: auto-compare if baseline GGUF provided
- [ ] Output: detailed regression report (what changed, why it matters)

### 3.6 Test Phase 3
- [ ] Test: `ucore health` → reports all green
- [ ] Test: simulate generation failure → circuit breaker prevents retry loop
- [ ] Test: `ucore feedback eval/results/feedback/history_guide.json --dry-run`
- [ ] Test: pipeline traces logged for all stages
- [ ] Test: regression detection flags performance drop
- [ ] Manual: review logs from a full pipeline run

**Phase 3 Success Criteria**:
- ✅ Feedback loop works without Onyx
- ✅ Health checks pass on every run
- ✅ Circuit breaker prevents cascading failures
- ✅ Pipeline traces enable easy debugging
- ✅ Regression detection alerts on metric drops

**Time Estimate**: 2 days

---

## ✅ Phase 4: Documentation & Handoff (Week 2.5)
**Goal**: Updated docs, migration guide, clear examples

### 4.1 Update Core Documentation
- [ ] Update `docs/TRAINING_WORKFLOW_CONTEXT.md`:
  - [ ] Remove all Onyx sections
  - [ ] Add section: "Generation Techniques" (deterministic, ollama, openai)
  - [ ] Add section: "Knowledge Base Structure"
  - [ ] Update generation flow diagram (remove Onyx)
- [ ] Update `AGENTS.md`:
  - [ ] Replace "Onyx generation (v2)" section with deterministic explanation
  - [ ] Update CLI examples (remove `--technique onyx`)
  - [ ] Add example: `./ucore generate subjects/npc.json --technique deterministic`
  - [ ] Add example: `./ucore generate subjects/npc.json --technique deterministic --concept-focus dialogue,teaching`
- [ ] Update `README.md`:
  - [ ] Simplify quick start (no Onyx setup needed)
  - [ ] Add link to `DETERMINISTIC_GENERATION.md`
  - [ ] Update architecture diagram

### 4.2 Create New Documentation
- [ ] Create `docs/DETERMINISTIC_GENERATION.md`:
  - [ ] Explain: how deterministic generator works
  - [ ] Show: knowledge_base structure
  - [ ] Show: reproducibility example (seed → same output)
  - [ ] Show: fallback chain behavior
  - [ ] Troubleshoot: common generation issues
- [ ] Create `docs/KNOWLEDGE_BASE_CURATION.md`:
  - [ ] For domain experts: how to improve knowledge bases
  - [ ] Edit `knowledge_base/domain_concepts/{npc}.json`
  - [ ] Edit `knowledge_base/prompt_templates.yaml`
  - [ ] Test improvements locally before committing
- [ ] Create `docs/VALIDATION_GATES.md`:
  - [ ] Explain: validation checks
  - [ ] Show: how to run `ucore validate`
  - [ ] Explain: --strict mode vs warnings
  - [ ] Common validation errors + fixes

### 4.3 Create Migration Guide
- [ ] Create `docs/ONYX_REMOVAL_MIGRATION.md`:
  - [ ] For existing users: what changed?
  - [ ] How to upgrade: pull latest code, regenerate datasets
  - [ ] Breaking changes: `--technique onyx` no longer works
  - [ ] Recommended path: regenerate with `--technique deterministic`
  - [ ] Fallback path: if quality issues, try `--technique ollama`
  - [ ] Support: who to contact, where to report issues
- [ ] Create `docs/TROUBLESHOOTING.md`:
  - [ ] "Generation is non-deterministic" → likely bug in version, update
  - [ ] "Dataset validation fails" → run `ucore validate --strict` to see errors
  - [ ] "Training crashes with OOM" → try `--preset safe-any`
  - [ ] "Model quality dropped" → check regression detection report

### 4.4 Create Examples & Templates
- [ ] Create `knowledge_base/examples/`:
  - [ ] `history_guide_knowledge_base.json` (example for domain expert review)
  - [ ] `chef_assistant_knowledge_base.json` (example)
  - [ ] `new_npc_template.json` (template for creating new NPCs)
- [ ] Create `tests/fixtures/`:
  - [ ] `valid_dataset.jsonl` (perfect example, all checks pass)
  - [ ] `invalid_dataset.jsonl` (demonstrates validation failures)
  - [ ] Sample validation reports (JSON + HTML)

### 4.5 Test Phase 4
- [ ] Review all docs: grammar, clarity, accuracy
- [ ] Test: New user can follow README → create NPC in <30 min
- [ ] Test: Domain expert can follow curation guide → improve knowledge base
- [ ] Manual: verify all links work, no dead references

**Phase 4 Success Criteria**:
- ✅ All documentation updated and accurate
- ✅ Migration guide clear for existing users
- ✅ New NPCs can be created in <30 min
- ✅ Knowledge base examples provided

**Time Estimate**: 1.5 days

---

## ✅ Phase 5: Hardening & Optimization (Week 3)
**Goal**: Performance, error recovery, final robustness

### 5.1 Performance Optimization
- [ ] Benchmark deterministic generation:
  - [ ] Target: <1s for 72 examples
  - [ ] Profile: identify bottlenecks
  - [ ] Optimize: template loading, JSON serialization
  - [ ] Measure: actual vs target
- [ ] Optimize validation:
  - [ ] Target: <2s for dataset validation
  - [ ] Cache: diversity metrics between runs
  - [ ] Benchmark: actual vs target
- [ ] Optimize full pipeline:
  - [ ] Target: <5 min end-to-end (gen + sanitize + train + export + eval)
  - [ ] Profile: which stages are slow
  - [ ] Parallelize: where possible (multiple NPCs)

### 5.2 Error Recovery & Resilience
- [ ] Implement partial recovery:
  - [ ] If generation fails midway, save partial dataset
  - [ ] On retry, resume from checkpoint
  - [ ] Show progress: "Generated 45/72 examples, resuming..."
- [ ] Automatic retry with backoff:
  - [ ] Transient failures: retry up to 3 times
  - [ ] Exponential backoff: 1s, 2s, 4s
  - [ ] Log each retry attempt
- [ ] Graceful degradation:
  - [ ] If optional service unavailable (Ollama), continue with deterministic
  - [ ] If Supabase tracking unavailable, log locally only
  - [ ] Never fail the pipeline for optional features

### 5.3 Add Telemetry (Opt-In)
- [ ] Create `scripts/telemetry.py`:
  - [ ] Track: generation time, dataset quality metrics, training time, eval results
  - [ ] Send to W&B: if `--wandb` flag used
  - [ ] Include: NPC key, technique used, git commit hash
  - [ ] Privacy: no user PII, fully opt-in
- [ ] Usage: `./ucore train --wandb` automatically logs telemetry
- [ ] Analysis: identify trends (which techniques work best, etc.)

### 5.4 Security Hardening
- [ ] Validate all input:
  - [ ] JSON schema validation for specs
  - [ ] Sanitize file paths (prevent directory traversal)
  - [ ] Validate JSONL format before processing
- [ ] Sanitize LLM outputs:
  - [ ] When using Ollama/OpenAI, escape special characters
  - [ ] Check for injection attempts
  - [ ] Log suspicious inputs
- [ ] Rate limiting:
  - [ ] External API calls (Ollama, OpenAI) limited
  - [ ] Prevent accidental DDoS of local Ollama
  - [ ] Configurable rate limits

### 5.5 Final Comprehensive Testing
- [ ] End-to-end tests (all NPCs):
  - [ ] `test_full_pipeline_history_guide()`: gen → sanitize → train → export → eval
  - [ ] `test_full_pipeline_chef_assistant()`: same
  - [ ] Both should complete in <5 min
- [ ] Stress tests:
  - [ ] Generate large datasets (1000+ examples)
  - [ ] Validate under load
  - [ ] Concurrent generation (multiple NPCs at once)
- [ ] Recovery tests:
  - [ ] Simulate network errors during generation
  - [ ] Simulate OOM during training
  - [ ] Simulate corrupted GGUF files
  - [ ] All should fail gracefully with clear error messages
- [ ] Cross-platform tests:
  - [ ] Linux (RTX 3060 6GB)
  - [ ] macOS (if available)
  - [ ] Windows (WSL2)

### 5.6 Final Review & Documentation
- [ ] Code review: all new code reviewed for quality
- [ ] Test coverage: verify 85%+ coverage maintained
- [ ] Linting: `black`, `pylint` pass on all scripts
- [ ] Docs: final pass on all documentation
- [ ] Changelog: add entry for "Onyx Removal" release

### 5.7 Test Phase 5
- [ ] All benchmarks hit targets (<1s gen, <2s validation, <5min pipeline)
- [ ] All recovery scenarios handled gracefully
- [ ] Zero regressions from Onyx removal:
  - [ ] Model quality unchanged or improved
  - [ ] Training time unchanged
  - [ ] GGUF exports identical format
- [ ] CI/CD green on all platforms

**Phase 5 Success Criteria**:
- ✅ <1s deterministic generation
- ✅ 85%+ test coverage maintained
- ✅ <5 min full pipeline end-to-end
- ✅ Zero unhandled failures in 10 test runs
- ✅ Project deemed "production-ready"

**Time Estimate**: 1.5 days

---

## 📊 Final Checklist (Completion)

### Before Release
- [ ] All phases complete (1-5)
- [ ] All tests passing: `pytest tests/ -v`
- [ ] CI/CD pipeline green
- [ ] Code coverage >85%
- [ ] Docs updated and reviewed
- [ ] Migration guide approved
- [ ] Benchmarks verified
- [ ] Final user testing (if applicable)

### Release Checklist
- [ ] Create git tag: `v2.0.0-onyx-removal`
- [ ] Update CHANGELOG.md with full details
- [ ] Push to main branch
- [ ] Announce to team/users
- [ ] Monitor for issues in first 48h

### Post-Release
- [ ] Archive old Onyx documentation
- [ ] Monitor W&B telemetry for quality metrics
- [ ] Gather user feedback
- [ ] Plan improvements based on telemetry

---

## 🎯 Success Metrics (Final)

| Metric | Target | Status |
|--------|--------|--------|
| Onyx code removed | 100% | ☐ |
| Deterministic generation reproducibility | 100% | ☐ |
| Generation speed | <1s | ☐ |
| Dataset validation speed | <2s | ☐ |
| Full pipeline duration | <5 min | ☐ |
| Test coverage | 85%+ | ☐ |
| Tests passing | 100% | ☐ |
| Regression detection | Active | ☐ |
| Health checks | All green | ☐ |
| Documentation | Complete | ☐ |
| User feedback | Positive | ☐ |

---

## 📞 Questions for Clarification

Before starting Phase 1, confirm:

1. **Knowledge Base Content**: Should I extract initial content from current reference_docs, or wait for your review?
2. **Validation Strictness**: Should `--strict` block training on quality issues, or just warn?
3. **Fallback Default**: Should `--technique ollama` require explicit flag, or auto-attempt if available?
4. **Domain Expert Review**: Do you plan to manually review/improve knowledge bases after Phase 1?
5. **Testing Requirements**: Is 85% unit test coverage sufficient, or target higher?

---

## 🚀 Ready to Begin

All preparation done. Waiting for approval to start Phase 1.

**Next Step**: Review this checklist, answer clarification questions, and give go-ahead for Phase 1 implementation.
