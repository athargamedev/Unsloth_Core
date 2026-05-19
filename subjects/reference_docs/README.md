# Reference Doc Pattern

Reference docs are source material for dataset generation. They are not
generated artifacts.

Minimum contract:

- Store each primer under `subjects/reference_docs/`.
- Use Markdown with one H1 title and at least 5 H2 sections.
- Include at least 20 concrete bullet facts/examples and at least 250 words.
- Include safety, refusal, boundary, misconception, or myth notes.
- Avoid placeholder language: `TODO`, `TBD`, `FIXME`, `stub`, `placeholder`.

Recommended sections:

- `## Scope and NPC Use`
- `## Core Concepts`
- `## Domain Facts`
- `## Worked Examples or Scenarios`
- `## Common Misconceptions`
- `## Safety Boundaries`
- `## Vocabulary`

Check generation readiness with:

```bash
./ucore validate-spec subjects/NPC_specs/{npc_key}.json --generation-ready
```
