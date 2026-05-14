# Subject Specification Schema (subjects/*.json)

> **Cross-reference**: For the complete dataset lifecycle, generation techniques, sanitization rules, training data flow, and minimum requirements, see [`docs/DATASET_STRUCTURE_AND_LOGIC.md`](../DATASET_STRUCTURE_AND_LOGIC.md).

The `subjects/` directory contains JSON files that define the identity, knowledge, and behavior of an NPC. These files are the primary input for the dataset generation pipeline.

## 📂 Top-Level Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `npc_key` | `string` | A unique `snake_case` identifier (e.g., `alchemy_master`). |
| `npc_name` | `string` | The display name in `PascalCase` (e.g., `AlchemyMaster`). |
| `identity` | `object` | Core personality and background details. |
| `teaching` | `object` | Domain expertise and pedagogical style. |
| `dialogue` | `object` | Conversational rules and styles. |
| `quest` | `object` | Interactive scenarios for the NPC. |
| `refusal` | `object` | Safety boundaries and redirect policies. |
| `research_queries` | `array` | Queries used by NotebookLM/Ollama to gather data. |
| `system_prompt` | `string` | The final system message used during inference. |
| `dataset` | `object` | Configuration for dataset balancing. |
| `technique` | `string` | Optional preferred dataset technique for this subject (for example `docs` for the Workflow Assistant). |

---

## 👤 `identity` Object
Defines who the NPC is.
- `personality`: Adjectives describing their vibe (e.g., "Grumpy but wise").
- `background`: Their history or profession.
- `mannerisms`: Verbal tics or specific ways of speaking.

## 🎓 `teaching` Object
Defines what the NPC knows and how they teach it.
- `expertise`: List of topics the NPC is an expert in.
- `approach`: Their teaching method (e.g., "Hands-on demonstrations").
- `difficulty_levels`: List of intended audience levels (e.g., `["beginner", "expert"]`).

## 💬 `dialogue` Object
Defines the conversational constraints.
- `conversation_style`: General tone (e.g., "Formal and archaic").
- `max_sentences`: Maximum length of a single response.
- `example_topics`: List of things a player might ask about.

## 🛡️ `refusal` Object
Critical for safety and boundary handling.
- `boundaries`: List of forbidden topics.
- `redirect_policy`: How to steer the user back to valid topics.

## 🔍 `research_queries` Array
Used by the generation stage to find source material.
```json
{
  "query": "The history of alchemy in the 16th century",
  "mode": "fast",
  "from": "web",
  "source_policy": "text-web"
}
```

## 📊 `dataset` Object
Controls the distribution of examples in the generated `.jsonl` file.
```json
"dataset": {
  "technique": "docs",
  "corpus_manifest": "docs/corpora/workflow_assistant_docs.json",
  "examples_per_category": {
    "identity": 8,
    "teaching": 32,
    "dialogue": 16,
    "quest": 8,
    "refusal": 8
  }
}
```

- `technique`: Optional preferred dataset technique for this spec.
- `corpus_manifest`: Optional curated manifest used by the `docs` technique.

---

## 💡 Best Practices
1. **Consistency**: Ensure the `system_prompt` incorporates elements from `identity` and `dialogue`.
2. **Specific Queries**: Use detailed queries to avoid generic or repetitive training data.
3. **Small Steps**: For complex NPCs, start with a small `examples_per_category` count to verify the generation quality before scaling up.
4. **Curated corpus**: Use `dataset.corpus_manifest` only for checked-in docs and structured reports; avoid logs, outputs, secrets, or machine-local state.
