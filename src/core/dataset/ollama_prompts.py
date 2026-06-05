from __future__ import annotations

import re

GENERIC_FILLER_REPLACEMENTS = [
    r"once you understand this, everything falls into place naturally\. ?",
    r"once you understand this, everything falls into place\. ?",
    r"the rest falls into place\. ?",
    r"let me tell you something about it\. ?",
]

PROMPT_LEAK_PATTERNS = [
    r"evaluation contract",
    r"contract role",
    r"source snippets",
    r"memory retention scenarios",
    r"guided archive note",
    r"category:\s*",
    r"difficulty:\s*",
]


def clean_generic_filler(text: str, concept: str = "this topic") -> str:
    cleaned = text or ""
    for pattern in GENERIC_FILLER_REPLACEMENTS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    if cleaned.strip() == (text or "").strip() and any(
        phrase in cleaned.lower()
        for phrase in ["everything falls into place", "once you understand"]
    ):
        cleaned = re.sub(
            r"[^.!?]*(everything falls into place|once you understand)[^.!?]*[.!?]?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned.split()) < 8:
        cleaned = f"For {concept}, focus on one concrete cause, effect, or example before connecting it to the bigger picture."
    return cleaned


def contains_prompt_leak(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in PROMPT_LEAK_PATTERNS)


def build_category_generation_prompt(
    category: str,
    concept_str: str,
    npc_name: str,
    player_role: str = "player",
    subject: str = "history",
    concepts_str: str = "chronology or sources",
) -> str:
    return {
        "identity": f"Write a very short first-person self-introduction for {npc_name}. Say who you are, directly answer what you do, name one focus related to {subject}, such as {concepts_str}, avoid generic storyteller language, and keep it to 1-2 sentences.",
        "teaching": f"Write a question from a {player_role} about '{concept_str}' and a direct answer. Answer directly, include one concrete fact or example from the reference doc, and add one practical implication for the player. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
        "dialogue": f"Write a casual turn about '{concept_str}' with an in-character answer. Answer directly, add one grounded detail or example, and include why it matters in play. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
        "quest": f"Write a challenge-style exchange about '{concept_str}' that stays practical and in character. Include one concrete action step, one example, and one decision-useful implication. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
        "refusal": f"Write an out-of-scope question for {npc_name}, state the boundary clearly, and redirect to a safe in-scope alternative. Do not add an unrelated fact or drift to another topic. Include 'Instead, I can help with...' plus one concrete in-scope topic related to {subject}, such as {concepts_str}. Keep it to 1-2 sentences.",
    }.get(
        category,
        f"Generate a concise educational dialogue about '{concept_str}' with one concrete detail.",
    )


def build_generation_prompt(
    npc_name: str,
    system_prompt: str,
    setting: str,
    relationship: str,
    category: str,
    concept_str: str,
    category_prompt: str,
    grounding: str,
    player_role: str,
    max_sentences: int,
    max_chars: int,
    multi_turn: bool = False,
    turn_instruction: str = "",
    json_shape: str = "",
) -> str:
    prompt = [
        f"Generate a concise training dialogue in JSON format for NPC '{npc_name}'.",
        "",
        f"System Prompt: {system_prompt}",
        f"Setting: {setting or 'Not specified'}",
        f"Player Relationship: {relationship or 'Not specified'}",
        "",
        f"Task: {category_prompt}{turn_instruction}",
        f"Category: {category}",
        f"Concept: {concept_str}{grounding}",
        "",
        "Instructions:",
        f"- The user message must sound like an in-game player ({player_role}).",
        f"- The assistant response must follow {npc_name}'s system prompt perfectly.",
        "- Use the reference doc for grounding when available.",
        f"- Speak 1-{max_sentences} sentences (MAXIMUM {max_chars} characters).",
        "- NEVER use markdown lists, bullet points, bolding, or tables (keep text clean for game UI).",
        "- Never mention being an AI or language model.",
        "",
        "Return JSON:",
        "{",
        json_shape,
        "}",
    ]
    return "\n".join(prompt)
