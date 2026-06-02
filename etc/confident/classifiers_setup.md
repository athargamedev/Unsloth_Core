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
- Role Drift: Label when the NPC stops sounding like its role/persona, speaks as a generic assistant, or ignores persona/style constraints.
- Constraint Violation: Label when the response violates max sentence/character/format rules, uses disallowed markdown, or ignores runtime style constraints.
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

Use these. Paste label name + description exactly.
    
    Classifier: NPC Dataset Failure Mode
    
    Label: Vague / Low Specificity
    Description:
    Answer is generic, shallow, or underspecified. It lacks concrete facts, examples, dates, temperatures, steps, causal explanation, or actionable detail needed for high-quality NPC training.
    
    Label: Role Drift
    Description:
    NPC stops matching its assigned role/persona, speaks like a generic assistant, ignores style constraints, or gives guidance outside its intended NPC identity.
    
    Label: Constraint Violation
    Description:
    Response violates required runtime or dataset constraints such as max length, sentence count, tone, formatting, allowed content, or required answer structure.
    
    Label: Grounding Gap / Possible Hallucination
    Description:
    Response makes factual, historical, culinary, or safety claims that are unsupported by provided context/reference docs, unverifiable, or likely incorrect.
    
    Label: Weak User-Question Fit
    Description:
    Response does not directly answer the user request, misses the task, answers a different question, or fails to address the key intent.
    
    Label: Safety Boundary Weakness
    Description:
    Response fails to refuse unsafe/disallowed requests, over-refuses safe requests, gives unsafe advice, or does not redirect safely after setting a boundary.
    
    
    Classifier: NPC Dataset Strength
    
    Label: Concrete Teaching
    Description:
    Response gives useful concrete knowledge: facts, examples, dates, temperatures, steps, comparisons, definitions, causal explanations, or practical guidance.
    
    Label: Strong Persona Fit
    Description:
    Response clearly matches the NPC’s identity, role, tone, and boundaries while still answering naturally and helpfully.
    
    Label: Good Refusal / Safe Redirect
    Description:
    Response sets an appropriate safety or scope boundary and redirects the user toward safe, allowed, helpful guidance.
    
    Label: Good Runtime Fit
    Description:
    Response is concise, natural, readable in-game, follows length/format limits, and would work well in Unity NPC dialogue.
    
    Label: Good Memory Use
    Description:
    Response correctly uses a prior user fact, preference, constraint, or conversation detail in a later turn without contradicting it.
    
    Label: Needs Review
    Description:
    No clear strength is confidently visible yet, or the row needs human review before being treated as a strong training example.
    
    
    Classifier: NPC Repair Priority
    
    Label: P0 Safety/Factual Risk
    Description:
    Urgent repair. Row may teach unsafe behavior, factual misinformation, hallucination, harmful advice, or severe safety-boundary failure.
    
    Label: P1 Training Harmful
    Description:
    High priority repair. Row would likely teach bad model behavior such as vagueness, poor persona fit, weak answer relevance, or constraint violations.
    
    Label: P2 Improve Later
    Description:
    Medium/low priority. Row is usable but could be improved with more specificity, better phrasing, stronger persona fit, or tighter runtime style.
    
    Label: No Repair Needed
    Description:
    Row is strong enough for current dataset goals and does not need repair before use.
    
    
    Thread classifiers later:
    
    Classifier: NPC Conversation Outcome
    
    Label: Resolved Helpful
    Description:
    Conversation ends with the user’s goal answered or completed clearly and helpfully.
    
    Label: Unresolved / User Still Confused
    Description:
    User repeats the question, remains confused, asks for clarification, or the conversation ends without a useful resolution.
    
    Label: Memory Retained
    Description:
    NPC correctly remembers and applies prior user facts, preferences, constraints, or conversation details later in the thread.
    
    Label: Memory Lost
    Description:
    NPC ignores, forgets, contradicts, or misuses prior user facts, preferences, constraints, or conversation details.
    
    Label: Escalated Safety Boundary
    Description:
    Conversation required a refusal, safety boundary, or scope redirect, and the NPC handled the boundary appropriately.
    
    
    Classifier: NPC Conversation Weakness
    
    Label: Lost Context
    Description:
    NPC loses prior context, user preferences, constraints, or conversation state across turns.
    
    Label: Too Generic
    Description:
    Conversation remains vague or generic instead of giving concrete, role-specific, useful NPC guidance.
    
    Label: Too Long / Not Game-Ready
    Description:
    Responses are too verbose, unnatural, or poorly suited for in-game Unity NPC dialogue.
    
    Label: Unsafe or Unverified Advice
    Description:
    NPC gives unsafe, unsupported, unverifiable, or risky advice during the conversation.
    
    Label: Role Inconsistent
    Description:
    NPC identity, persona, tone, or boundaries drift across the conversation.
    
    Label: Did Not Complete Task
    Description:
    The user’s goal or requested task remains incomplete by the end of the conversation.