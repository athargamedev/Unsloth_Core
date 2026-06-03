# spec-grounding-curator

Spec, primer, and grounding readiness specialist.

## Owns

- `data/npcs/specs/<npc>.json`
- `data/npcs/reference_docs/<npc>_primer.md`
- Reference doc contract.
- Concept coverage and dialogue constraints.
- Generation readiness for active NPCs only.

## Commands

```bash
./ucore validate-spec data/npcs/specs/<npc>.json --generation-ready
```

## Review

- Primer exists, is Markdown, has concrete grounding, and supports the spec.
- Concepts are specific enough for grounded generation.
- Dialogue limits and metadata requirements remain intact.
- Refusal boundaries are represented in both spec and primer.

## Handoff

Validated spec path, primer gaps, warnings/errors, and narrow recommended edits.
