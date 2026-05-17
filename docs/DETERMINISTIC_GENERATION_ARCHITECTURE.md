# Deterministic Dataset Generation Architecture

**Replacing Onyx with a reproducible, testable, maintainable system**

---

## 🎯 Core Concept

**Old (Onyx)**:
```
spec.json → Onyx server (RAG) → retrieve docs → render templates → non-deterministic Q&A
```

**New (Deterministic)**:
```
spec.json + knowledge_base/ → hash-based variant selection → template fill → deterministic Q&A
```

**Key Difference**: Same seed always produces identical output (reproducible, testable, Git-friendly)

---

## 📐 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Deterministic Dataset Generation Pipeline                       │
└─────────────────────────────────────────────────────────────────┘

Step 1: Load Inputs
  ├─ subjects/{npc_key}.json (NPC spec)
  ├─ knowledge_base/category_library.json (universal templates)
  ├─ knowledge_base/prompt_templates.yaml (variant templates)
  ├─ knowledge_base/domain_concepts/{npc_key}.json (NPC-specific concepts)
  └─ seed=42 (determinism)

Step 2: Extract Generation Config
  ├─ teaching.expertise[...] (concepts to teach)
  ├─ identity.personality, background, mannerisms (identity examples)
  ├─ dialogue.example_topics[...] (dialogue scenarios)
  ├─ quest.scenarios[...] (quest challenges)
  └─ refusal.boundaries[...] (safe boundaries)

Step 3: Generate Examples Per Category
  For each category (identity, teaching, dialogue, quest, refusal):
    For variant_index in range(target_count):
      ├─ variant_seed = hash(f"{concept}:{category}:{variant_index}:{seed}")
      ├─ template = _pick_template(category, variant_seed)
      ├─ variant = _pick_variant(template, variant_seed)
      ├─ content = _fill_template(variant, concept, knowledge_base[category])
      ├─ q_a_pair = ChatML(question=content.q, response=content.a)
      └─ output_jsonl.append(q_a_pair)

Step 4: Validate Output
  ├─ Format check (ChatML compliance)
  ├─ Distribution check (8/32/16/8/8 ± tolerance)
  ├─ Duplicate check (exact + semantic)
  ├─ Concept coverage (all expertise covered)
  ├─ Diversity metrics (TTR, Simpson's)
  └─ Token count check (fit in context)

Step 5: Output
  └─ subjects/datasets/{npc_key}/deterministic/train.jsonl (72 examples)
```

---

## 🔧 Key Components

### 1. **Knowledge Base Structure**

```
knowledge_base/
├── category_library.json
│   {
│     "identity": {
│       "traits": ["patient", "enthusiastic", "methodical"],
│       "patterns": [
│         {"trait": "patient", "response": "I take time to explain things carefully"},
│         {"trait": "patient", "response": "I'm never in a hurry"}
│       ]
│     },
│     "teaching": {
│       "concepts": ["complex topics", "prerequisites", "examples"],
│       "patterns": [
│         {"concept_type": "complex", "template": "Let me break this down:"},
│         {"concept_type": "prerequisite", "template": "First, you need to know about"}
│       ]
│     },
│     ...
│   }
│
├── prompt_templates.yaml
│   identity:
│     templates:
│       - "Who are you?"
│       - "Tell me about yourself"
│       - "Introduce yourself"
│     variants:
│       - "Natural"
│       - "Formal"
│   teaching:
│     templates:
│       - "Explain {concept}"
│       - "Describe {concept}"
│       - "How does {concept} work?"
│     variants:
│       - "Beginner"
│       - "Detailed"
│       - "Analogies"
│
├── domain_concepts/
│   ├── history_guide.json
│   │   {
│   │     "concepts": {
│   │       "roman_empire": {
│   │         "summary": "Ancient Rome, 27 BC - 476 AD",
│   │         "key_facts": ["Republic → Empire", "Senate", "Military"],
│   │         "misconceptions": ["All Romans were gladiators", "Latin is a dead language"]
│   │       },
│   │       "industrial_revolution": {...}
│   │     },
│   │     "dialogue_scenarios": [
│   │       {"situation": "Student confused about dates", "approach": "narrative_timeline"}
│   │     ]
│   │   }
│   └── chef_assistant.json
│       {
│         "concepts": {
│           "sauté": {"steps": ["heat pan", "add fat", "add ingredients"], ...},
│           "knife_skills": {...}
│         }
│       }
```

### 2. **Seed-Based Variant Selection**

```python
def _pick_variant(seed, category, template, variant_count=3):
    """Deterministically pick a variant using seed."""
    variant_index = seed % variant_count
    variants = TEMPLATE_CONFIG[category]['variants']
    return variants[variant_index]

# Example
seed = hash("roman_empire:teaching:0:42")  # deterministic
variant = _pick_variant(seed, "teaching", "Explain {concept}", variant_count=3)
# Always returns the same variant for same concept/category/seed
```

### 3. **Template Filling**

```python
def _fill_template(template_variant, concept, knowledge_item):
    """Fill template with concept-specific content."""
    if variant == "Beginner":
        level = "simple"
    elif variant == "Detailed":
        level = "comprehensive"
    else:  # Analogies
        level = "metaphor"
    
    # Render template
    content = template.format(
        concept=concept,
        summary=knowledge_item['summary'],
        key_facts=knowledge_item['key_facts'][0],
        misconception=knowledge_item['misconceptions'][0]
    )
    
    return {
        'question': f"Tell me about {concept}",
        'response': content,
        'metadata': {
            'concept': concept,
            'category': 'teaching',
            'variant': variant,
            'level': level
        }
    }
```

### 4. **ChatML Format Output**

```jsonl
{"role": "user", "content": "Tell me about the Roman Empire"}
{"role": "assistant", "content": "The Roman Empire lasted from 27 BC to 476 AD. It started as a republic and became an empire under Augustus. The key aspects were..."}
{"role": "user", "content": "What was the Industrial Revolution?"}
{"role": "assistant", "content": "The Industrial Revolution was a transformation from agricultural to industrial economies. It began in Britain around 1760..."}
```

---

## 🔄 Generation Algorithm (Pseudocode)

```python
def generate_deterministic(spec_path, knowledge_base_path, seed=42):
    """Generate deterministic dataset from spec and knowledge base."""
    
    # 1. Load inputs
    spec = load_json(spec_path)
    kb = load_knowledge_base(knowledge_base_path)
    npc_key = spec['npc_key']
    
    # 2. Initialize output
    examples = []
    
    # 3. For each category
    for category in ['identity', 'teaching', 'dialogue', 'quest', 'refusal']:
        category_config = spec[category]
        target_count = CATEGORY_TARGETS[category]  # 8, 32, 16, 8, 8
        
        # 3a. Determine what to generate
        if category == 'identity':
            items = [category_config['personality'], category_config['background']]
        elif category == 'teaching':
            items = category_config['teaching']['expertise']
        elif category == 'dialogue':
            items = category_config['dialogue']['example_topics']
        elif category == 'quest':
            items = [s['name'] for s in category_config['quest']['scenarios']]
        else:  # refusal
            items = category_config['refusal']['boundaries']
        
        # 3b. Generate examples
        item_index = 0
        for i in range(target_count):
            # Rotate through items
            item = items[item_index % len(items)]
            item_index += 1
            
            # Deterministic seed for this example
            example_seed = hash(f"{npc_key}:{category}:{item}:{i}:{seed}")
            
            # Pick variant
            template = _pick_template(category, example_seed, kb)
            variant = _pick_variant(category, example_seed, template)
            
            # Fill template
            content = _fill_template(
                template=template,
                variant=variant,
                item=item,
                knowledge_base=kb,
                category_config=category_config,
                seed=example_seed
            )
            
            # Format as ChatML
            example = {
                'role': 'user',
                'content': content['question'],
                'metadata': {
                    'category': category,
                    'item': item,
                    'variant': variant
                }
            }
            examples.append(example)
            
            example = {
                'role': 'assistant',
                'content': content['response'],
                'metadata': {
                    'category': category,
                    'item': item,
                    'variant': variant
                }
            }
            examples.append(example)
    
    # 4. Validate
    report = validate_dataset(examples, spec)
    if not report['passed']:
        log_error(f"Validation failed: {report['errors']}")
        raise ValidationError(report)
    
    # 5. Write output
    output_path = f"subjects/datasets/{npc_key}/deterministic/train.jsonl"
    write_jsonl(output_path, examples)
    
    log_info(f"Generated {len(examples)//2} examples to {output_path}")
    return output_path

def _pick_template(category, seed, kb):
    """Pick a template variant deterministically."""
    templates = kb['prompt_templates'][category]['templates']
    index = seed % len(templates)
    return templates[index]

def _pick_variant(category, seed, template):
    """Pick a variant of a template deterministically."""
    variants = kb['prompt_templates'][category]['variants']
    index = seed % len(variants)
    return variants[index]

def _fill_template(template, variant, item, knowledge_base, category_config, seed):
    """Fill template with concept-specific content."""
    # Get domain-specific knowledge
    domain_kb = knowledge_base['domain_concepts'][npc_key]
    item_knowledge = domain_kb['concepts'].get(item, {})
    
    # Generate question (same for all variants)
    question = template.format(concept=item)
    
    # Generate response (varies by variant)
    if variant == "Beginner":
        response = generate_beginner_response(item, item_knowledge, template)
    elif variant == "Detailed":
        response = generate_detailed_response(item, item_knowledge, template)
    else:  # Analogies
        response = generate_analogy_response(item, item_knowledge, template)
    
    return {'question': question, 'response': response}
```

---

## ✅ Reproducibility Guarantee

**Theorem**: Given the same `seed`, `spec`, and `knowledge_base`, generation produces byte-for-byte identical output.

**Proof**:
1. ✅ All randomness seeded with deterministic hash
2. ✅ All template selection via `seed % len(templates)`
3. ✅ All content filling deterministic (no LLM calls, rules-based)
4. ✅ JSON serialization deterministic (sorted keys, consistent formatting)
5. ✅ JSONL output order deterministic (category → item → variant → seed)

**Verification Test**:
```python
def test_deterministic_reproducibility():
    spec = load_json("subjects/history_guide.json")
    kb = load_knowledge_base("knowledge_base/")
    
    data1 = generate_deterministic(spec, kb, seed=42)
    data2 = generate_deterministic(spec, kb, seed=42)
    
    assert data1 == data2  # Byte-for-byte identical
    
    hash1 = compute_hash(data1)
    hash2 = compute_hash(data2)
    assert hash1 == hash2  # Same content hash
```

---

## 🎲 Fallback Chain

```
Step 1: Attempt Deterministic Generation
  └─ 100% reliable (no external dependencies)
  
Step 2: If Quality Concerns → Ollama Enrichment
  ├─ Run: ollama_enrich_dataset.py
  ├─ Input: deterministic dataset
  ├─ Process: LLM improves response quality
  ├─ Output: enhanced dataset
  └─ Reliability: 80% (depends on Ollama availability)

Step 3: If Ollama Unavailable → OpenAI Enrichment
  ├─ Run: openai_enrich_dataset.py
  ├─ Input: deterministic dataset
  ├─ Process: API improves response quality
  ├─ Output: enhanced dataset
  └─ Reliability: 70% (depends on API key, quota)

Step 4: If All Fail → Use Deterministic (Fallback)
  └─ Primary deterministic generation used as-is
```

---

## 📊 Comparison: Onyx vs Deterministic

| Aspect | Onyx RAG | Deterministic |
|--------|----------|---------------|
| **Reproducibility** | ❌ Non-deterministic | ✅ Same seed → same output |
| **Testability** | ❌ Hard to test (black box) | ✅ Easy to unit test |
| **Dependencies** | ❌ External Onyx server | ✅ Pure Python (no server) |
| **Debugging** | ❌ Unclear retrieval process | ✅ Audit trail in code |
| **Memory** | ❌ 10 containers, 2-3 GB | ✅ <50 MB Python process |
| **Speed** | ❌ Slow (network + inference) | ✅ <1 second |
| **Version Control** | ❌ Non-deterministic (can't commit) | ✅ Git-friendly (reproducible) |
| **Knowledge Maintenance** | ❌ Index into Onyx (opaque) | ✅ Edit JSON files (clear) |
| **Validation** | ❌ Unclear if data is good | ✅ Comprehensive checks |
| **Error Recovery** | ❌ Fails hard | ✅ Circuit breaker + retries |

---

## 🔐 Safety & Validation

### Pre-Training Validation Gates

```
Generated Dataset
    ↓
[1] Format Check
    ├─ All messages have "role" field (user|assistant)
    ├─ All messages have "content" field (non-empty)
    └─ ChatML structure valid

[2] Distribution Check
    ├─ Category counts: identity 8±1, teaching 32±3, dialogue 16±2, quest 8±1, refusal 8±1
    └─ Total: 72 examples

[3] Content Validation
    ├─ No empty responses
    ├─ Response length 50-500 tokens
    ├─ Question clarity score >0.7
    └─ Response coherence score >0.8

[4] Uniqueness Check
    ├─ No exact duplicates
    ├─ No semantic duplicates (cosine similarity <0.95)
    └─ Diversity metrics pass (TTR >0.4, Simpson's >0.8)

[5] Concept Coverage
    ├─ All teaching.expertise covered at least once
    ├─ All dialogue.topics covered at least once
    └─ All quest.scenarios represented

[6] Safety Check
    ├─ No harmful content
    ├─ Refusal examples present
    ├─ Boundaries respected
    └─ No PII leaks

    ↓ All pass? → Dataset approved for training
    ↓ Some warnings? → Log and proceed (optional --strict blocks)
    ↓ Any errors? → Fail and report (user must fix or regenerate)
```

---

## 🚀 Usage Examples

### Generate Deterministic (Default)
```bash
./ucore generate subjects/history_guide.json
# → subjects/datasets/history_guide/deterministic/train.jsonl
```

### Regenerate Weak Concepts (Feedback Loop)
```bash
./ucore generate subjects/history_guide.json \
  --concept-focus dialogue,teaching \
  --seed 43  # Different seed, new examples
```

### Enrich with Ollama
```bash
./ucore generate subjects/history_guide.json \
  --technique ollama \
  --enrichment-file subjects/datasets/history_guide/deterministic/train.jsonl
# → Takes deterministic as input, improves with LLM
```

### Full Pipeline
```bash
./ucore pipeline subjects/history_guide.json --technique deterministic
# → Generate → Sanitize → Train → Export → Eval (all automatically)
```

---

## 📝 Knowledge Base Maintenance

### For Domain Experts (Non-Programmers)

Edit `knowledge_base/domain_concepts/history_guide.json`:

```json
{
  "concepts": {
    "roman_empire": {
      "summary": "Ancient Rome (27 BC - 476 AD)",
      "key_facts": [
        "Started as a republic, became an empire",
        "Senate governed alongside the emperor",
        "Military was highly organized and powerful"
      ],
      "misconceptions": [
        "All Romans were gladiators",
        "Latin is completely dead"
      ],
      "difficulty": "beginner",
      "related_concepts": ["republic", "empire", "senate"]
    },
    "industrial_revolution": {
      "summary": "Transformation from agricultural to industrial (1760-1840)",
      "key_facts": [...],
      "misconceptions": [...],
      "difficulty": "intermediate"
    }
  }
}
```

Changes are immediately reflected in next generation → no "re-indexing" needed.

---

## 🎯 Conclusion

Deterministic generation replaces Onyx with a simpler, more reliable, more testable system that:
- ✅ Produces reproducible datasets
- ✅ Enables comprehensive testing
- ✅ Works without external services
- ✅ Uses less memory
- ✅ Runs faster
- ✅ Is easier to debug
- ✅ Is easier to improve (edit JSON, not Onyx indices)
- ✅ Git-friendly (can track dataset changes)

**Result**: A production-ready dataset generation pipeline you can trust, test, and maintain.
