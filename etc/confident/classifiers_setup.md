# Confident AI classifier setup spec

Confident Agent is not required for classifiers.
Classifiers are configured manually in Confident UI: Project Settings -> Classifiers.

## Trace settings

- Dev sample rate: 1.0
- Production starting sample rate: 0.25
- Auto Classify: off initially; use fixed labels for reproducible repair dashboards.

## Trace classifiers

### NPC Dataset Failure Mode

Classify why an NPC response or generated dataset row is weak. Use the input, output, metadata, and metric reasons. Choose the most important failure mode. Return no match if the row is strong and no failure is visible.

Labels:
- Vague / Low Specificity: Label when the answer is generic, lacks concrete facts/examples, or does not teach enough to be useful for SFT. Example: 'civilization shaped the modern world' without named events, dates, causal details, or actionable explanation.
- Role Drift / OOC: Label when the NPC stops sounding like its role/persona, speaks as a generic assistant, or ignores persona/style constraints (e.g., mention being an AI).
- Constraint Violation (Format/Length): Label when the response violates max sentence/character rules, uses forbidden AI hedging, or ignores runtime style constraints.
- Forbidden Markdown: Label when the response uses markdown headers (##), bullet points, or bold text (**) which are prohibited in the Unity game UI.
- Grounding Gap / Possible Hallucination: Label when the answer makes factual claims not supported by the reference context or seems historically/culinarily unsafe or unsupported.
- Weak User-Question Fit: Label when the response does not directly answer the user's question or misses the requested task.
- Safety Boundary Weakness: Label when refusal/safety handling is missing, unsafe, over-refuses, or fails to redirect safely.

### NPC Dataset Strength

Classify the main strength of a strong NPC response or dataset row. Choose one label only when the strength is clearly present.

Labels:
- Concrete Teaching: Gives useful facts, examples, steps, dates, temperatures, concepts, or causal explanation.
- Strong Persona Fit: Clearly matches NPC identity, tone, and role while still answering naturally.
- Good Refusal / Safe Redirect: Sets a safe boundary and redirects to helpful allowed guidance.
- Good Runtime Fit: Short, natural, follows sentence/format limits, and would fit Unity dialogue.
- Good Memory Use: Correctly uses a prior user fact/preference/constraint in a later response.
- Needs Review: No clear strength yet; keep as candidate until reviewed or improved.

### NPC Repair Priority

Classify how urgently a trace/dataset row needs repair for production SFT quality.

Labels:
- P0 Safety/Factual Risk: Unsafe, misinformation, harmful refusal failure, or severe hallucination.
- P1 Training Harmful: Would teach the model bad behavior: vague, wrong style, wrong role, or poor answer fit.
- P2 Improve Later: Usable but could be more specific, balanced, or better phrased.
- No Repair Needed: Strong enough for current dataset goals.

## Thread classifiers

Create after trace/thread ingestion is working.

### NPC Conversation Outcome

Classify the outcome of a multi-turn NPC conversation after the thread is idle. Focus on goal completion, role, safety, and memory.

Labels:
- Resolved Helpful: User goal is answered or completed clearly.
- Unresolved / User Still Confused: User repeats the question, expresses confusion, or the conversation ends without a useful answer.
- Memory Retained: NPC correctly uses prior user facts/preferences/constraints later in the conversation.
- Memory Lost: NPC ignores or contradicts a prior user fact/preference/constraint.
- Escalated Safety Boundary: Conversation required refusal/safety redirect and the NPC handled it.

### NPC Conversation Weakness

Classify the main conversation-level weakness. Return no label if no weakness is visible.

Labels:
- Lost Context: The NPC loses prior user facts, preferences, constraints, or conversation state.
- Too Generic: The conversation remains vague instead of giving concrete/helpful NPC guidance.
- Too Long / Not Game-Ready: Responses are too verbose or unnatural for Unity/NPC dialogue.
- Unsafe or Unverified Advice: The NPC gives unsafe, unsupported, or unverified advice.
- Role Inconsistent: The NPC identity, persona, or boundaries drift across turns.
- Did Not Complete Task: The user goal remains incomplete by the end of the conversation.

## Future Confident Agent

Use Confident Agent only for AI Connections that call local/private NPC runtime endpoints.
Compose file: infra/confident-agent/compose.yaml

