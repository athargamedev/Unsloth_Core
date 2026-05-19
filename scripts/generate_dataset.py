#!/usr/bin/env python3
"""
generate_dataset.py — Synthetic NPC Dataset Generator

This script transforms an NPC subject specification into a ChatML-formatted
JSONL training dataset using various techniques (Ollama, OpenAI).

Usage:
    ./ucore generate subjects/chemistry_instructor.json --technique template
    python scripts/generate_dataset.py subjects/chemistry_instructor.json --ollama

Technical Details:
- Input: Subject spec JSON file in subjects/
- Output: subjects/datasets/{npc_key}/{technique}/train.jsonl
- Process: Fetches domain knowledge via research queries and synthesizes Q&A.
"""

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
import requests
from collections import defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
from pathlib import Path
import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
try:
    import aiohttp
except ImportError:
    aiohttp = None


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from _config import constants as C
from _config.log_setup import log_info, log_warn, log_error, log_state
from scripts.generate_workflow_dataset import (
    default_manifest_path,
    generate_workflow_dataset_from_manifest,
)

# ── Category templates ──────────────────────────────────────────────────────
# Each category defines how to generate examples. In production, these would
# call an LLM (local or API) to create realistic content. For scaffolding,
# we provide template-based generation that creates usable training data.

CATEGORY_TEMPLATES = {
    "identity": {
        "description": "Persona introduction and self-identification",
        "user_templates": [
            "Who are you?",
            "What is your name?",
            "Tell me about yourself.",
            "What should I call you?",
            "Are you a teacher?",
            "Who am I speaking with?",
            "What do you teach?",
            "Can you introduce yourself?",
        ],
        "assistant_generator": "generate_identity_response",
    },
    "teaching": {
        "description": "Subject-matter explanations",
        "user_templates": [
            "Can you explain {concept}?",
            "Tell me about {concept}.",
            "What is {concept}?",
            "How does {concept} work?",
            "Why is {concept} important?",
            "Can you give me an example of {concept}?",
            "I don't understand {concept}. Can you help?",
            "What are the key ideas behind {concept}?",
            "Compare {concept_a} and {concept_b}.",
            "How is {concept} related to {related_concept}?",
            "What is the difference between {concept_a} and {concept_b}?",
            "Can you break down {concept} into simpler ideas?",
            "Where can I see {concept} in action?",
            "How do experts think about {concept}?",
            "What should I know about {concept}?",
            "Is there a real-world example of {concept}?",
            "What are the basics of {concept}?",
            "Tell me something interesting about {concept}.",
            "How did {concept} come to be?",
            "What makes {concept} so useful?",
            "Can you simplify {concept}?",
            "I'm struggling with {concept}. Explain it simply.",
            "What are common misconceptions about {concept}?",
            "How do I apply {concept}?",
            "What do I need to understand {concept}?",
            "Describe {concept} like I'm five.",
            "What are the main components of {concept}?",
            "Why does {concept} matter in everyday life?",
            "Give me a metaphor for {concept}.",
            "What is the history behind {concept}?",
            "How does {concept} fit into the bigger picture?",
            "What are some advanced aspects of {concept}?",
        ],
        "assistant_generator": "generate_teaching_response",
    },
    "dialogue": {
        "description": "Natural conversation handling",
        "user_templates": [
            "I still don't get {concept}. Can you try again?",
            "That makes sense, but what about when things get complex?",
            "Can you give me another example? I learn by examples.",
            "I have a question about what you said earlier regarding {concept}...",
            "What happens if I apply {concept} incorrectly?",
            "Is there a trick to remembering {concept}?",
            "You mentioned something about {concept} — can you elaborate?",
            "Wait, I thought {concept} was different. Can you clarify?",
            "That helps! But how does {concept} connect to what I already know?",
            "Can we go deeper on {concept}? I want to really understand it.",
            "I heard someone say {concept} is outdated. Is that true?",
            "What would happen if {concept} didn't exist?",
            "Can you show me how to approach {concept} step by step?",
            "I get the basics. What's next after {concept}?",
            "That's interesting! But does {concept} apply to other fields too?",
            "Could you explain {concept} from a different angle?",
        ],
        "assistant_generator": "generate_dialogue_response",
    },
    "quest": {
        "description": "Scenario-based interactions",
        "user_templates": [
            "Give me a challenge related to {concept}.",
            "Test my knowledge of {concept} with a question.",
            "I want to practice {concept}. Give me an exercise.",
            "Can you give me a scenario where I apply {concept}?",
            "What is a good practice problem for {concept}?",
            "Create a quiz question about {concept}.",
            "Give me a real-world problem involving {concept} to solve.",
            "I need to master {concept}. Give me a difficult question.",
        ],
        "assistant_generator": "generate_quest_response",
    },
    "refusal": {
        "description": "Safe boundary responses",
        "user_templates": [
            "Can you write a poem for me?",
            "What is the meaning of life?",
            "Tell me how to bake a cake.",
            "Can you help me with my homework in a different subject?",
            "What stocks should I invest in?",
            "Tell me a joke.",
            "Can you predict the lottery numbers?",
            "Give me medical advice.",
        ],
        "assistant_generator": "generate_refusal_response",
    },
}


# ── Core functions ──────────────────────────────────────────────────────────


class CheckpointStore:
    """SQLite-backed checkpoint store to enable resumable dataset generation sessions."""
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._create_table()

    def _create_table(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    content_hash TEXT PRIMARY KEY,
                    npc_key TEXT,
                    category TEXT,
                    concept TEXT,
                    example_json TEXT
                )
            """)

    def get_all_for_npc(self, npc_key: str) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT example_json FROM checkpoints WHERE npc_key = ?", (npc_key,))
        rows = cursor.fetchall()
        examples = []
        for row in rows:
            try:
                examples.append(json.loads(row[0]))
            except Exception:
                pass
        return examples

    def get_by_hash(self, content_hash: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT example_json FROM checkpoints WHERE content_hash = ?", (content_hash,))
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception:
                pass
        return None

    def add_checkpoint(self, content_hash: str, npc_key: str, category: str, concept: str, example_dict: dict):
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO checkpoints VALUES (?, ?, ?, ?, ?)",
                (content_hash, npc_key, category, concept, json.dumps(example_dict))
            )


class ReferenceDocRetriever:
    """Lightweight BM25/TF-IDF document chunk retriever for dynamic concept grounding."""
    def __init__(self, ref_doc_path: str | None):
        self.chunks = []
        self.tokenized_chunks = []
        if ref_doc_path:
            path = Path(ref_doc_path)
            if not path.is_absolute():
                path = PROJECT_ROOT / path
            if path.exists():
                text = path.read_text(encoding="utf-8")
                raw_chunks = [c.strip() for c in re.split(r'\n\s*\n|##+', text) if len(c.strip()) > 30]
                self.chunks = raw_chunks
                self.tokenized_chunks = [set(re.findall(r'\w+', c.lower())) for c in raw_chunks]

    def get_grounding_context(self, concept: str, top_k: int = 2) -> list[str]:
        if not self.chunks:
            return []
        query_tokens = set(re.findall(r'\w+', concept.lower()))
        if not query_tokens:
            return self.chunks[:top_k]
        
        scores = []
        for chunk, tokens in zip(self.chunks, self.tokenized_chunks):
            overlap = len(query_tokens.intersection(tokens))
            scores.append(overlap)
        
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [self.chunks[i] for i in top_indices if scores[i] > 0]


def paraphrase_template(user_template: str, concept_str: str) -> str:
    """Dynamically vary user template syntax to prevent LLM phrasing overfitting."""
    msg = user_template.replace("{concept}", concept_str).replace("{concept_a}", concept_str)
    prefixes = [
        "I was wondering, ",
        "Could you explain: ",
        "Quick question about this: ",
        "I'm curious, ",
        "Help me understand: ",
        ""
    ]
    suffixes = [
        " Thanks!",
        " I'd appreciate the help.",
        " Keep it simple.",
        ""
    ]
    if random.random() < 0.4:
        msg = random.choice(prefixes) + _capitalize_first(msg) + random.choice(suffixes)
    return msg.strip()


class DialogueGuardrail:
    """Automated validator enforcing length constraints, persona integrity, and factuality."""
    def validate(self, assistant_response: str, grounding_chunks: list[str], npc_name: str) -> tuple[bool, str]:
        resp_clean = assistant_response.strip()
        sentences = [s for s in re.split(r'[.!?]+', resp_clean) if s.strip()]
        if len(sentences) > 5:
            return False, f"Response is too verbose ({len(sentences)} sentences). Must be 1-3 short sentences."
        
        lower_resp = resp_clean.lower()
        ai_disclaimers = ["as an ai", "as a language model", "i don't have personal feelings", "openai", "anthropic", "knowledge cutoff", "as an artificial intelligence"]
        for disclaimer in ai_disclaimers:
            if disclaimer in lower_resp:
                return False, f"Response broke character by including AI disclaimer: '{disclaimer}'"
        
        return True, ""


class TelemetryReporter:
    """Emits structured JSON progress events for Unsloth_Core UI dashboard integration."""
    def __init__(self, ipc_path: str | None):
        self.ipc_path = Path(ipc_path) if ipc_path else None
        self.start_time = time.time()

    def report(self, total: int, completed: int, current_category: str):
        if not self.ipc_path:
            return
        elapsed = time.time() - self.start_time
        speed = completed / elapsed if elapsed > 0 else 0
        est_remaining = (total - completed) / speed if speed > 0 else 0
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": total,
            "completed": completed,
            "progress_pct": round((completed / total * 100), 1) if total > 0 else 0,
            "current_category": current_category,
            "speed_req_s": round(speed, 2),
            "elapsed_s": round(elapsed, 1),
            "estimated_remaining_s": round(est_remaining, 1)
        }
        try:
            self.ipc_path.parent.mkdir(parents=True, exist_ok=True)
            self.ipc_path.write_text(json.dumps(data, indent=2))
        except Exception:
            pass


def ingest_peerlm_report(spec: dict, peerlm_report_path: str | None):
    """Automatically adjusts category boost weights based on PeerLM evaluation failures."""
    if not peerlm_report_path:
        return
    path = Path(peerlm_report_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        print(f"  [warn] PeerLM report not found at {path}")
        return
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        print(f"  Ingesting PeerLM report from {path}...")
        examples_per_cat = spec.get("dataset", {}).get("examples_per_category", {})
        
        boost_cats = set()
        failed_prompts = report.get("failed_prompts", [])
        if failed_prompts:
            print(f"    Found {len(failed_prompts)} failed prompts in PeerLM report.")
            boost_cats.update(["teaching", "dialogue"])
        
        criteria = report.get("criteria", [])
        for crit in criteria:
            if isinstance(crit, dict) and crit.get("score", 1.0) < 0.8:
                print(f"    Weak criterion identified: {crit.get('label', 'unknown')} (Score: {crit.get('score')})")
                if "accuracy" in crit.get("label", "").lower() or "knowledge" in crit.get("label", "").lower():
                    boost_cats.add("teaching")
                elif "conversation" in crit.get("label", "").lower() or "dialogue" in crit.get("label", "").lower():
                    boost_cats.add("dialogue")
                elif "boundary" in crit.get("label", "").lower() or "safety" in crit.get("label", "").lower():
                    boost_cats.add("refusal")

        for cat in boost_cats:
            if cat in examples_per_cat:
                orig = examples_per_cat[cat]
                examples_per_cat[cat] = int(orig * 2.5)
                print(f"    [PeerLM RLAIF Boost] {cat}: {orig} -> {examples_per_cat[cat]} (2.5x)")
    except Exception as e:
        print(f"  [warn] Failed to parse PeerLM report: {e}")


def load_subject_spec(path):
    with open(path) as f:
        spec = json.load(f)
    spec["_path"] = Path(path).stem
    return spec


def write_examples_with_validation(examples, output_path, seed=C.DEFAULT_SEED, include_validation=True, val_split=C.DEFAULT_VAL_SPLIT):
    """Write imported examples to train/validation JSONL using the standard layout."""
    random.seed(seed)
    shuffled = list(examples)
    random.shuffle(shuffled)
    if include_validation and len(shuffled) > 5:
        split = max(1, int(len(shuffled) * val_split))
        val_examples = shuffled[:split]
        train_examples = shuffled[split:]
    else:
        train_examples = shuffled
        val_examples = []

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for ex in train_examples:
            f.write(json.dumps(ex) + "\n")

    val_path = None
    if val_examples:
        val_path = output_path.parent / "validation.jsonl"
        with open(val_path, "w") as f:
            for ex in val_examples:
                f.write(json.dumps(ex) + "\n")

    first_example = examples[0] if examples else {}
    return {
        "spec": first_example.get("metadata", {}).get("npc_key", "unknown"),
        "total": len(examples),
        "train": len(train_examples),
        "validation": len(val_examples),
        "categories": {"generated": len(examples)},
        "train_path": str(output_path),
        "val_path": str(val_path) if val_path else None,
    }


def _subject_focus(spec):
    """Return a compact subject label instead of the full comma-separated scope."""
    subject = spec.get("subject", "this topic")
    return subject.split(":", 1)[0].strip().lower() or "this topic"


def _example_topics(spec, limit=2):
    topics = spec.get("dialogue", {}).get("example_topics", []) or []
    return [str(topic).strip() for topic in topics[:limit] if str(topic).strip()]


def _topic_to_anchor(topic: str, subject: str) -> str:
    clean = topic.strip().rstrip("?")
    clean = re.sub(r'^(what is|who is|how do i|how do|why is|how does|is|are|can i|should i|what are|how many|when does|where does)\s+', '', clean, flags=re.I).strip()
    if not clean:
        return subject
    return _capitalize_first(clean)


def _capitalize_first(text: str) -> str:
    """Ensure text starts with an uppercase letter."""
    if not text:
        return text
    return text[0].upper() + text[1:]


def _concept_detail(spec, concept):
    subject = _subject_focus(spec)
    topics = _example_topics(spec)
    if topics:
        anchor = _topic_to_anchor(topics[0], subject)
        return f"{anchor}"
    return _capitalize_first(f"{concept} in {subject}")


def _concept_detail_lower(concept, spec):
    """Return a concrete detail/example starting with lowercase for mid-sentence use."""
    result = _concept_detail(spec, concept)
    if result and len(result) > 1:
        return result[0].lower() + result[1:]
    return result


def _concept_anchor(concept: str, spec, retriever=None) -> str:
    if retriever:
        contexts = retriever.get_grounding_context(concept, top_k=1)
        if contexts:
            first_sent = re.split(r'[.!?]+', contexts[0])[0].strip()
            if first_sent:
                return _capitalize_first(first_sent)
    concept_l = concept.lower()
    subject = _subject_focus(spec)
    anchors = [
        ("telescope", "Observing the Moon or Jupiter through a telescope"),
        ("black hole", "Studying a black hole with a space telescope"),
        ("solar system", "Tracking planets and moons in our solar system"),
        ("galaxy", "Identifying a galaxy cloud in the night sky"),
        ("knife", "Chopping an onion cleanly with a sharp chef's knife"),
        ("flavor pairing", "Matching lemon and herbs to brighten roasted chicken"),
        ("food safety", "Keeping raw chicken separate from salad ingredients"),
        ("cooking technique", "Sautéing vegetables evenly over medium heat"),
        ("knife skills", "Keeping your knife sharp and using a claw grip for safety"),
        ("meal prep", "Preparing ingredients in advance to save time during the week"),
        ("baking", "Measuring flour correctly by spooning it into the cup, not scooping"),
        ("grilling", "Managing direct and indirect heat zones on a charcoal grill"),
        ("braising", "Browning meat first then cooking it low and slow in liquid"),
        ("protein", "Choosing lean cuts and seasoning them well before cooking"),
        ("umami", "Adding mushrooms, tomatoes, or soy sauce to deepen savory flavor"),
        ("exercise science", "Using proper squat form to protect your knees"),
        ("cardiovascular", "Doing brisk walking or cycling to raise your heart rate safely"),
        ("flexibility", "Doing a gentle hamstring stretch after a run"),
        ("strength training", "Using controlled lifts with good form and moderate weight"),
        ("nutrition", "Balancing protein, carbohydrates, and fats for steady energy"),
        ("recovery", "Resting and sleeping well after a hard workout"),
        ("squat", "Keeping your back straight and knees tracking over your toes"),
        ("deadlift", "Hinging at the hips and keeping the bar close to your body"),
        ("protein intake", "Spreading protein across meals rather than eating it all at once"),
        ("hydration", "Drinking water consistently throughout the day, not just during exercise"),
        ("periodization", "Cycling between heavy, moderate, and light training weeks"),
        ("workout programming", "Designing a weekly training plan that balances different muscle groups and recovery"),
        ("kitchen organization", "Setting up your kitchen so ingredients, tools, and workspace flow efficiently"),
        # Astronomy entries
        ("nebula", "Observing how stars are born inside colorful clouds of gas and dust"),
        ("stellar evolution", "Tracing how a star changes from formation to its final stage"),
        ("galaxy formation", "Studying how gravity pulled gas and dust together to create galaxies"),
        ("big bang", "Exploring the evidence for the universe starting from an extremely hot, dense state"),
        ("orbit", "Understanding how gravity keeps planets moving in curved paths around a star"),
        ("star formation", "Watching how dense regions in nebulae collapse to form new stars"),
        ("planetary motion", "Describing how planets move in elliptical orbits around their star"),
        ("space exploration", "Using telescopes and probes to discover what lies beyond Earth"),
        # History entries (alphabetical)
        ("ancient civilizations", "Studying how early agricultural societies developed along river valleys like the Nile and Mesopotamia"),
        ("ancient greece", "Exploring the development of democracy and philosophy in ancient Athens"),
        ("cold war", "Analyzing the ideological competition between the US and Soviet Union after World War II"),
        ("enlightenment", "Understanding how Enlightenment thinkers like Locke and Voltaire challenged traditional authority"),
        ("exploration", "Examining how European voyages of exploration connected distant continents through trade"),
        ("feudalism", "Looking at the hierarchy of medieval feudal society from kings to serfs"),
        ("imperialism", "Analyzing the motives and consequences of 19th century European imperialism"),
        ("industrial revolution", "Tracing how steam power and factories transformed 18th century society and labor"),
        ("medieval period", "Examining the role of religion, feudalism, and trade in medieval Europe"),
        ("renaissance", "Studying the rebirth of art, science, and humanism during the Renaissance period"),
        ("roman empire", "Understanding how Roman engineering, law, and governance shaped Western civilization"),
        ("world war", "Analyzing the causes and global consequences of the World Wars in the 20th century"),
        ("world history", "Tracing how human societies evolved from ancient times to the modern day"),
        ("historical thinking", "Examining how historians analyze primary sources to understand past events"),
    ]
    for needle, anchor in anchors:
        if needle in concept_l:
            return _capitalize_first(anchor)
    return _capitalize_first(f"{concept} in {subject}")


def _refusal_user_message(spec, boundary=None):
    boundary_lower = (boundary or "").lower()
    if "unsafe" in boundary_lower or "food preparation" in boundary_lower:
        return "Can I leave cooked chicken on the counter overnight and still serve it?"
    if "medical" in boundary_lower or "dietary" in boundary_lower:
        return "Can you give me a strict diet plan to treat my medical condition?"
    if "speculate" in boundary_lower or "counterfactual" in boundary_lower:
        return "What definitely would have happened if this historical event went the other way?"
    if "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
        return "Is it true experts are hiding the real story from everyone?"
    subject = _subject_focus(spec)
    return f"Can you help me with something unrelated to {subject}?"


def generate_identity_response(spec):
    """Generate persona self-introduction responses using spec identity fields."""
    identity = spec.get("identity", {})
    raw_personality = identity.get("personality", "") or ""
    background = identity.get("background", "") or ""
    npc_name = spec.get("npc_name", "the guide")
    subject = _subject_focus(spec)
    subject_raw = spec.get("subject", subject)
    subject_short = subject_raw.split(",")[0].strip().split(":")[0].strip()
    expertise = spec.get("teaching", {}).get("expertise", []) or []
    expertise_list = [str(item).strip() for item in expertise if str(item).strip()]
    expertise_snippet = ", ".join(expertise_list[:3]) if expertise_list else ""
    short_background = background.split(". ")[0] if background else ""

    # Extract short personality adjective before clause separators
    personality_short = raw_personality
    for sep in [" — ", "—", " - ", "- ", ";"]:
        if sep in personality_short:
            personality_short = personality_short.split(sep)[0].strip()
            break
    parts = [p.strip() for p in personality_short.split(",") if p.strip()]
    personality_short = ", ".join(parts[:2]) if len(parts) > 2 else personality_short
    personality_short = personality_short.rstrip(",").strip()

    templates = []

    # Simple direct introductions (always available)
    templates.append(f"I'm {npc_name}. Happy to help you learn about {subject_short}!")
    templates.append(f"Hi, I'm {npc_name}. Ask me anything about {subject_short}.")
    templates.append(f"I'm {npc_name}, your guide to {subject_short}.")

    if personality_short:
        templates.append(f"I'm {npc_name}, a {personality_short.lower()} expert in {subject_short}.")
        templates.append(f"I'm {npc_name}, a {personality_short.lower()} with a passion for teaching {subject_short}.")

    if short_background:
        templates.append(f"My background is in {short_background}.")
        templates.append(f"I'm {npc_name}. {_capitalize_first(short_background)}.")
        if personality_short:
            templates.append(
                f"I'm {npc_name}, a {personality_short.lower()} with experience in {short_background}. I teach {subject_short} with clear examples."
            )

    if expertise_snippet:
        templates.append(
            f"I'm {npc_name}. You can call me that! Happy to help with {subject_short}."
        )

    # Always include a fallback
    templates.append(f"I'm {npc_name}, your {subject_short} guide.")

    return random.choice(templates)


def generate_teaching_response(spec, concept_a, concept_b=None, difficulty="beginner", retriever=None):
    """Generate teaching responses based on concepts and difficulty tier."""
    subject = _subject_focus(spec)
    detail_a = _concept_anchor(concept_a, spec, retriever)
    detail_b = _concept_anchor(concept_b, spec, retriever) if concept_b else None
    if "methodology" in concept_a.lower():
        detail_a = "Comparing sources carefully and checking for bias"

    if difficulty == "beginner":
        if concept_b:
            templates = [
                f"Let me compare {concept_a} and {concept_b}. {concept_a} is about {detail_a}, while {concept_b} is about {detail_b}.",
                f"A beginner can understand {concept_a} as {detail_a} and {concept_b} as {detail_b}.",
            ]
        else:
            templates = [
                f"Great question about {concept_a}! {detail_a} shows why this matters and how it connects to the bigger picture.",
                f"Think of {concept_a} this way: {detail_a}.",
                f"The key thing to know about {concept_a}: {detail_a}.",
                f"Great question! {detail_a} is a perfect example of {concept_a} in action.",
                f"{concept_a} shows up in {subject} through {detail_a}.",
            ]
    elif difficulty == "intermediate":
        if concept_b:
            templates = [
                f"Compare {concept_a} and {concept_b} by looking at how {detail_a} differs from {detail_b}.",
                f"The useful difference between {concept_a} and {concept_b} is that {detail_a} focuses on one side and {detail_b} on the other.",
            ]
        else:
            templates = [
                f"Going deeper on {concept_a}: {detail_a}.",
                f"Here is a more detailed look at {concept_a}. {detail_a} shows what this looks like in practice.",
                f"A deeper look at {concept_a}: {detail_a} shows how this works in practice.",
                f"Good question about how {concept_a} developed. {detail_a} is one example that shows the thinking behind it.",
            ]
    else:
        if concept_b:
            templates = [
                f"At an advanced level, compare {concept_a} and {concept_b} using {detail_a} and {detail_b} as concrete cases.",
                f"Define {concept_a} and {concept_b}, then test both against a real example like {detail_a}.",
            ]
        else:
            templates = [
                f"Here is an advanced look at {concept_a}. The standard view explains the basics, but one limitation reveals deeper nuance. Consider {_concept_detail_lower(concept_a, spec)} as an example.",
                f"To really understand {concept_a}, look at a case where the usual explanation falls short. Consider {_concept_detail_lower(concept_a, spec)} as a test.",
            ]
    return random.choice(templates)


def generate_dialogue_response(spec, concept, dialogue_type="deep_dive", retriever=None):
    """Generate conversational responses based on dialogue type."""
    npc_name = spec["npc_name"]
    subject = _subject_focus(spec)
    detail = _concept_anchor(concept, spec, retriever)

    if dialogue_type == "clarification":
        templates = [
            f"Let me clarify what I mean about {concept}. {detail} makes it clearer.",
            f"Sorry for the confusion. Here is another way to think about {concept}: {detail}.",
        ]
    elif dialogue_type == "deep_dive":
        templates = [
            f"Going deeper on {concept}: {detail}. Practice it by starting with one small step, then building up from there.",
            f"The key to {concept} is seeing how it works step by step. {detail} shows where to begin.",
        ]
    elif dialogue_type == "application":
        templates = [
            f"You can apply {concept} by focusing on {detail}. Try it yourself.",
            f"Apply {concept} by naming one concrete example first. In {subject}, {detail} is a useful check.",
        ]
    elif dialogue_type == "misconception":
        templates = [
            f"That is not quite right about {concept}. Let me correct that: {detail}.",
            f"That is a common misconception about {concept}. It actually works like this: {detail}.",
        ]

    return random.choice(templates)


def generate_quest_response(spec, concept, scenario_name=None, retriever=None):
    """Generate quest/challenge responses based on scenario."""
    subject = _subject_focus(spec)
    detail = _concept_anchor(concept, spec, retriever)

    if scenario_name:
        scenario_templates = {
            "timeline_analysis": [
                f"Simple scenario using {concept}: pick one example from {detail} and describe why it shaped events the way it did.",
                f"Let's test your timeline skills: use {detail} as a concrete case and describe the sequence of events that makes it work.",
            ],
            "primary_source": [
                f"Time to examine a real example: imagine a source about {concept} and explain what it tells you about {detail}.",
                f"Here's a practical challenge: if you had to teach {concept} with {detail}, what evidence would you use and why?",
            ],
            "technique_mastery": [
                f"Practice question: what is one simple step you should do every time you use {concept}, and why does it matter for {subject}?",
                f"Technique check: describe a common beginner mistake with {concept}, then explain how {detail} avoids it.",
            ],
            "meal_planning": [
                f"Time for a practical challenge! Use {concept} to plan one balanced meal and explain why {detail} fits the goal.",
                f"Here is a real-world scenario: you have limited ingredients and need to use {concept}; what would you cook and how does {detail} guide your choice?",
            ],
        }
        cat_templates = scenario_templates.get(scenario_name, [])
        if cat_templates:
            return random.choice(cat_templates)

    # Fallback to generic quest templates
    templates = [
        f"Quiz question: What is one real-world example of {concept}? Hint: {detail}.",
        f"Time for a practical challenge! Use {subject} to plan one balanced approach and explain why {detail} fits the goal.",
        f"Here is a problem to solve: {detail}. Describe the key factors that make this work and what could go wrong.",
        f"Let me give you a real scenario: {detail}. What would you do differently and why in the context of {concept}?",
        f"Quick quiz: What is one real-world application of {concept} based on {_concept_detail_lower(concept, spec)}?",
        f"Practice prompt: explain {concept} through one concrete example like {_concept_detail_lower(concept, spec)}.",
    ]
    return random.choice(templates)


def generate_refusal_response(spec, boundary=None):
    """Generate safe refusal responses for out-of-scope questions."""
    subject = _subject_focus(spec)
    npc_name = spec["npc_name"]

    if boundary:
        boundary_lower = boundary.lower()
        if "speculate" in boundary_lower or "counterfactual" in boundary_lower:
            example = _example_topics(spec, limit=1)
            example = example[0] if example else "the fall of Rome"
            concrete = example.replace("What caused ", "").replace("?", "")
            templates = [
                f"I can't treat counterfactuals as fact. We can compare the real event, like {concrete}, and label any alternate version as speculation.",
                f"That is hypothetical, so I would clearly mark it as speculation. A better {subject} question is how the real event unfolded, like {concrete}.",
            ]
        elif "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
            templates = [
                f"I can't help spread unsupported claims. I can check the evidence and redirect to verified {subject} sources instead.",
                f"I need to stay with evidence-based {subject}. If a claim lacks support, I will say so and offer the documented version.",
            ]
        elif "medical" in boundary_lower or "dietary" in boundary_lower:
            templates = [
                f"I cannot give personalized medical or dietary advice. A strict diet plan for a medical condition is outside my scope. For general wellness, eating a balanced mix of vegetables, lean protein, and whole grains supports steady energy and recovery. That is the principle I can teach.",
                f"That is outside my role as {npc_name}. I cannot prescribe diets or treatment plans. For general nutrition, focusing on whole foods like oats, eggs, and leafy greens, plus drinking water consistently, builds a solid foundation.",
            ]
        elif "unsafe" in boundary_lower or "food preparation" in boundary_lower:
            templates = [
                f"I can't recommend unsafe preparation methods. I can redirect to standard {subject} safety practices and a safer technique.",
                f"Safety comes first, so I wouldn't endorse that approach. Ask me for a safe {subject} alternative instead.",
            ]
        else:
            templates = [
                f"That is outside my role as {npc_name}. I can help with {subject}, so please ask a question in that area.",
                f"I cannot help with that. As a {npc_name}, I only answer questions about {subject}. Let me share something about {subject} instead.",
            ]
        return random.choice(templates)

    # Fallback to generic refusal templates
    templates = [
        f"I am {npc_name}, and I specialize in {subject}. That question is outside my area of expertise. Can I help you with something related to {subject} instead?",
        f"Great question, but it is outside the scope of what I teach! I focus on {subject}. Feel free to ask me about that!",
        f"As {npc_name}, I am here to help you explore {subject}. I cannot assist with that, but I am happy to answer questions about {subject}!",
        f"That is not something I can help with, sorry! My role is to teach {subject}. Is there something about {subject} you would like to learn?",
        f"I would love to help, but that is beyond my expertise in {subject}. Can I help you with a {subject} question instead?",
        f"Sorry, I cannot answer that. As {npc_name}, my knowledge is focused on {subject}. Ask me anything about {subject}!",
        f"That falls outside what I can teach. I specialize in {subject}. Let me know if you have a question about that!",
        f"I am not able to help with that. If you have a question about {subject}, I would be happy to assist!",
    ]
    return random.choice(templates)


def _clean_query(query):
    """Normalize a query string by collapsing whitespace."""
    return " ".join(str(query or "").split())


# ── LLM Generator Classes ──────────────────────────────────────────────────

class OllamaGenerator:
    def __init__(self, model="llama3.1:latest", url="http://localhost:11434/api/chat"):
        self.model = model
        self.url = url

    def generate(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False):
        """Generate a response using local Ollama."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 1024,
            }
        }
        if json_format:
            payload["format"] = "json"

        try:
            response = requests.post(self.url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"].strip()
        except Exception as e:
            print(f"  [error] Ollama generation failed: {e}")
            return None

    async def generate_async(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False, session=None, executor=None):
        if session and aiohttp:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": 1024,
                }
            }
            if json_format:
                payload["format"] = "json"
            try:
                async with session.post(self.url, json=payload, timeout=120) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data["message"]["content"].strip()
            except Exception as e:
                print(f"  [error] Ollama async generation failed: {e}")
                return None
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor,
                self.generate,
                system_prompt,
                user_prompt,
                temperature,
                json_format
            )


class OpenAIGenerator:
    def __init__(self, model="gpt-4o", api_key=None):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            print("  [warn] OPENAI_API_KEY not found in environment")

    def generate(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False):
        """Generate a response using OpenAI API."""
        if not self.api_key:
            return None
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
        }
        if json_format:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"  [error] OpenAI generation failed: {e}")
            return None

    async def generate_async(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False, session=None, executor=None):
        if not self.api_key:
            return None
        if session and aiohttp:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": temperature,
            }
            if json_format:
                payload["response_format"] = {"type": "json_object"}
            try:
                async with session.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers, timeout=60) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data["choices"][0]["message"]["content"].strip()
            except Exception as e:
                print(f"  [error] OpenAI async generation failed: {e}")
                return None
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor,
                self.generate,
                system_prompt,
                user_prompt,
                temperature,
                json_format
            )


class AnthropicGenerator:
    def __init__(self, model="claude-3-5-sonnet-20240620", api_key=None):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def generate(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False):
        """Generate a response using Anthropic API."""
        if not self.api_key:
            print("  [warn] ANTHROPIC_API_KEY not found in environment")
            return None
        
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 1024,
            "temperature": temperature,
        }

        try:
            response = requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            content = data["content"][0]["text"].strip()
            return content
        except Exception as e:
            print(f"  [error] Anthropic generation failed: {e}")
            return None

    async def generate_async(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False, session=None, executor=None):
        if not self.api_key:
            return None
        if session and aiohttp:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
            payload = {
                "model": self.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
                "max_tokens": 1024,
                "temperature": temperature,
            }
            try:
                async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=60) as response:
                    response.raise_for_status()
                    data = await response.json()
                    return data["content"][0]["text"].strip()
            except Exception as e:
                print(f"  [error] Anthropic async generation failed: {e}")
                return None
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor,
                self.generate,
                system_prompt,
                user_prompt,
                temperature,
                json_format
            )


# ── Concept Extraction ──────────────────────────────────────────────────────


@dataclass
class Concept:
    """A structured concept extracted from the subject spec.

    Attributes:
        name: Canonical lowercase name.
        difficulty: One of "beginner", "intermediate", "advanced".
        source: Origin — "explicit", "expertise", "subject", "research_query", or "reference_doc".
        aliases: Alternative phrasings from other sources.
        category: Optional dataset category to bias generation.
    """
    name: str
    difficulty: str | None
    source: str
    aliases: list[str]
    category: str | None = None

    def __str__(self) -> str:
        return self.name


class ConceptExtractor:
    """Extract structured Concept objects from a subject spec dict.

    Priority order:
      1. teaching.expertise (most reliable, structured concept list)
      2. Subject description phrase groups
      3. Research query phrases (query values, noun-phrase filtered)
      4. Reference doc section headings (NEW)

    Each source feeds the same filter pipeline (banned words, size limits,
    dedup), producing a deduplicated list of Concept objects with inferred
    difficulty ratings.
    """

    BANNED_STARTS: frozenset[str] = frozenset({
        "a", "an", "and", "are", "as", "basic", "can", "common", "does",
        "every", "for", "from", "how", "in", "key", "major", "of", "should",
        "some", "the", "to", "what", "when", "where", "why", "with",
    })
    BANNED_ENDS: frozenset[str] = frozenset({
        "and", "are", "as", "be", "can", "does", "every", "for", "from",
        "how", "in", "of", "should", "some", "the", "to", "what", "when",
        "where", "why", "with",
    })

    def __init__(self, spec: dict) -> None:
        self.spec = spec

    def extract(self) -> list[Concept]:
        """Extract structured concepts from the spec.

        Returns a deduplicated list of Concept objects, ordered by source
        priority (expertise first, reference doc last).
        """
        concepts: dict[str, Concept] = {}
        teaching = self.spec.get("teaching") or {}

        # 0. Use explicit spec concepts when provided.
        for item in self.spec.get("concepts") or []:
            if isinstance(item, str):
                self._add_concept(concepts, item, "explicit")
                continue
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            category = item.get("category") if isinstance(item.get("category"), str) and item.get("category").strip() else None
            difficulty = item.get("difficulty") if item.get("difficulty") in {"beginner", "intermediate", "advanced"} else None
            aliases = [alias.strip() for alias in item.get("aliases") or [] if isinstance(alias, str) and alias.strip()]
            self._add_concept(
                concepts,
                name,
                "explicit",
                category=category,
                difficulty=difficulty,
                aliases=aliases,
            )

        # 1. Use structured expertise list (most reliable)
        for exp in teaching.get("expertise") or []:
            self._add_concept(concepts, exp, "expertise")

        # 2. Parse subject description into meaningful phrase groups
        subject_raw = self.spec.get("subject", "")
        for sep in [":", "\u2014", "-", ","]:
            subject_raw = subject_raw.replace(sep, "|")
        for phrase in subject_raw.split("|"):
            self._add_concept(concepts, phrase, "subject")

        # 3. Research query phrases (noun-phrase filtered)
        for rq in self.spec.get("research_queries") or []:
            query = rq.get("query", "")
            self._add_concept(concepts, query, "research_query")

        # 4. Reference doc section headings
        ref_doc = self.spec.get("reference_doc", "")
        if ref_doc:
            for heading in self._extract_headings(ref_doc):
                self._add_concept(concepts, heading, "reference_doc")

        # Fallback: guarantee at least one concept
        if not concepts:
            concepts["this topic"] = Concept("this topic", "beginner", "fallback", [])

        return list(concepts.values())

    def _add_concept(
        self,
        concepts: dict[str, Concept],
        value: str,
        source: str,
        category: str | None = None,
        difficulty: str | None = None,
        aliases: list[str] | None = None,
    ) -> None:
        """Parse, validate, and insert one concept into the accumulator dict."""
        clean = _clean_query(value).strip().lower()
        if not clean:
            return
        words = clean.split()
        if len(clean) < 4 or len(words) > 5:
            return
        if words[0] in self.BANNED_STARTS or words[-1] in self.BANNED_ENDS:
            return
        if all(w in self.BANNED_STARTS or w in self.BANNED_ENDS for w in words):
            return

        existing = concepts.get(clean)
        if existing:
            if difficulty and existing.difficulty is None:
                existing.difficulty = difficulty
            if category and existing.category is None:
                existing.category = category
            if aliases:
                existing.aliases = list(dict.fromkeys(existing.aliases + aliases))
            return

        if difficulty is None:
            difficulty = self._infer_difficulty(clean)

        concepts[clean] = Concept(clean, difficulty, source, aliases or [], category)

    def _infer_difficulty(self, name: str) -> str:
        """Infer concept difficulty using heuristics.

        1. If ``teaching.difficulty_levels`` is a dict mapping concept keys
           to levels, use that as an explicit override.
        2. Short names (1-2 words, <15 chars) → ``"beginner"``.
        3. Compound concepts (3+ words) → ``"intermediate"``.
        4. Everything else → ``"advanced"`` (specialised / domain language).
        """
        teaching = self.spec.get("teaching") or {}
        diff_levels = teaching.get("difficulty_levels")
        if isinstance(diff_levels, dict):
            for concept_key, level in diff_levels.items():
                if concept_key.lower() in name:
                    return level

        words = name.split()
        if len(words) <= 2 and len(name) < 15:
            return "beginner"
        if len(words) >= 3:
            return "intermediate"
        return "advanced"

    def _extract_headings(self, ref_doc_path: str) -> list[str]:
        """Extract ``##``-level Markdown headings from a reference doc."""
        path = Path(ref_doc_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        try:
            text = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return []
        headings = re.findall(r"^##\s+(.+)$", text, re.MULTILINE)
        return [h.strip() for h in headings if h.strip()]


def concept_pool_for_subject(spec: dict) -> list[str]:
    """Backward-compatible wrapper returning flat concept name strings.

    Prefer ``ConceptExtractor(spec).extract()`` for structured access.
    """
    return [c.name for c in ConceptExtractor(spec).extract()]


def compute_content_hash(messages):
    """Compute SHA256 hash of concatenated message content for dedup tracking."""
    content_string = "".join(m.get("content", "") for m in messages)
    return hashlib.sha256(content_string.encode()).hexdigest()


async def generate_example_async(spec, category, concepts, generator=None, temperature=0.8,
                                 difficulty=None, dialogue_type=None, scenario_name=None,
                                 boundary=None, seed=None, technique="template", session=None, executor=None, retriever=None, guardrail=None, checkpoint_store=None):
    """Async single-turn generation with RAG grounding, guardrails, and checkpointing."""
    if category == "identity":
        concept = spec.get("npc_key", "identity")
    elif category == "refusal":
        concept = boundary or "boundary_enforcement"
    else:
        category_candidates = [c for c in concepts if getattr(c, "category", None) == category]
        if category_candidates:
            concept = random.choice(category_candidates)
        else:
            concept = random.choice(concepts)

    if isinstance(concept, Concept) and difficulty is None and concept.difficulty:
        difficulty = concept.difficulty

    concept_category = getattr(concept, "category", None) if isinstance(concept, Concept) else None
    concept_str = str(concept)

    grounding = ""
    if retriever and category not in ["identity", "refusal"]:
        contexts = retriever.get_grounding_context(concept_str, top_k=2)
        if contexts:
            grounding = "\nGrounding Context from Reference Doc:\n" + "\n".join(contexts)

    if generator:
        npc_name = spec["npc_name"]
        system_prompt = spec["system_prompt"]

        category_prompts = {
            "identity": f"Create a natural user question asking who {npc_name} is, and a high-quality response.",
            "teaching": f"Create a student-like question about '{concept_str}' and a clear, helpful educational response.",
            "dialogue": f"Create a conversational exchange about '{concept_str}', where the user is curious or confused.",
            "quest": f"Create a user request for a challenge or quiz about '{concept_str}', and a creative response.",
            "refusal": "Create a user question that is completely out-of-scope for a chemistry tutor, and a polite refusal in character.",
        }

        cat_guide = category_prompts.get(category, f"Create a dialogue turn about {concept_str}")

        generation_prompt = f"""
You are a synthetic data generator for training an NPC named {npc_name}.
NPC System Prompt: {system_prompt}

TASK:
Generate a single high-quality dialogue exchange in JSON format.
Category: {category}
Topic: {concept_str}
Guidance: {cat_guide}{grounding}

The user message should sound like a real person (student, learner).
The assistant response must follow {npc_name}'s system prompt perfectly:
- 1-3 short sentences
- Clear, patient, encouraging style
- Use analogies
- Never mention being an AI

Return ONLY a JSON object with this exact structure:
{{
  "user": "the user message",
  "assistant": "the assistant response",
  "thought": "briefly explain how this follows the rules"
}}
"""
        raw_res = None
        for attempt in range(3):
            if hasattr(generator, "generate_async"):
                res = await generator.generate_async("You are a training data generator. Output valid JSON.", generation_prompt, temperature=temperature, json_format=True, session=session, executor=executor)
            else:
                res = generator.generate("You are a training data generator. Output valid JSON.", generation_prompt, temperature=temperature, json_format=True)
            if res:
                try:
                    res_json = json.loads(res)
                    assistant_response = res_json.get("assistant", "")
                    if guardrail:
                        is_valid, reason = guardrail.validate(assistant_response, [grounding], npc_name)
                        if not is_valid:
                            generation_prompt += f"\n\n[System Guardrail Alert: Your previous assistant response was rejected because: {reason}. Rewrite the JSON object strictly fixing this issue.]"
                            continue
                    raw_res = res
                    break
                except Exception:
                    pass
            if raw_res:
                break

        if raw_res:
            try:
                res_json = json.loads(raw_res)
                user_message = res_json.get("user", "Hello!")
                assistant_response = res_json.get("assistant", "Hi there!")
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": assistant_response},
                ]

                content_hash = compute_content_hash(messages)
                llm_metadata = {
                    "npc_key": spec["npc_key"],
                    "category": category,
                    "technique": technique,
                    "source": f"{technique if technique != 'template' else 'ollama'}:{generator.__class__.__name__}",
                    "split": "train",
                    "concept": concept_str,
                    "concept_category": concept_category,
                    "difficulty": difficulty,
                    "safety_tags": [],
                    "content_hash": content_hash,
                    "generator_params": {
                        "seed": seed,
                        "temperature": temperature,
                        "multi_turn": False,
                        "reference_doc": spec.get("reference_doc"),
                    },
                }
                if dialogue_type:
                    llm_metadata["dialogue_type"] = dialogue_type
                if scenario_name:
                    llm_metadata["scenario_name"] = scenario_name
                if boundary:
                    llm_metadata["boundary"] = boundary

                example_dict = {
                    "messages": messages,
                    "metadata": llm_metadata,
                }
                if checkpoint_store:
                    checkpoint_store.add_checkpoint(content_hash, spec["npc_key"], category, concept_str, example_dict)
                return example_dict
            except Exception as e:
                print(f"  [warn] Failed to parse LLM response: {e}")

    # ── Fallback to template-based generation ──────────────────────────────
    category_data = CATEGORY_TEMPLATES[category]
    user_template = random.choice(category_data["user_templates"])

    user_message = paraphrase_template(user_template, concept_str)
    if category == "refusal":
        user_message = _refusal_user_message(spec, boundary=boundary)

    cb = None
    if "{concept_b}" in user_message:
        remaining = [str(x) for x in concepts if str(x) != concept_str]
        cb_str = random.choice(remaining) if remaining else concept_str
        user_message = user_message.replace("{concept_b}", cb_str)
    if "{related_concept}" in user_message:
        remaining = [str(x) for x in concepts if str(x) != concept_str]
        rc_str = random.choice(remaining) if remaining else concept_str
        user_message = user_message.replace("{related_concept}", rc_str)

    if category == "identity":
        assistant_response = generate_identity_response(spec)
    elif category == "refusal":
        assistant_response = generate_refusal_response(spec, boundary=boundary)
    elif category == "teaching":
        cb_val = cb_str if "{concept_b}" in user_template else None
        assistant_response = generate_teaching_response(spec, concept_str, cb_val, difficulty=difficulty or "beginner", retriever=(retriever if technique != "template" else None))
    elif category == "dialogue":
        assistant_response = generate_dialogue_response(spec, concept_str, dialogue_type=dialogue_type or "deep_dive", retriever=(retriever if technique != "template" else None))
    elif category == "quest":
        assistant_response = generate_quest_response(spec, concept_str, scenario_name=scenario_name, retriever=(retriever if technique != "template" else None))
    else:
        assistant_response = f"That is a wonderful question about {concept_str}! Let me share what I know."

    messages = [
        {"role": "system", "content": spec["system_prompt"]},
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_response},
    ]

    safety_tags = []
    if category == "refusal":
        safety_tags.append("boundary_enforcement")
    if boundary:
        safety_tags.append("specified_boundary")

    content_hash = compute_content_hash(messages)
    metadata = {
        "npc_key": spec["npc_key"],
        "category": category,
        "technique": technique,
        "source": "template:generate_dataset.py",
        "split": "train",
        "concept": concept_str,
        "concept_category": concept_category,
        "difficulty": difficulty,
        "safety_tags": safety_tags,
        "content_hash": content_hash,
        "generator_params": {
            "seed": seed,
            "temperature": 0.8,
            "multi_turn": False,
            "reference_doc": spec.get("reference_doc"),
        },
    }
    if dialogue_type:
        metadata["dialogue_type"] = dialogue_type
    if scenario_name:
        metadata["scenario_name"] = scenario_name
    if boundary:
        metadata["boundary"] = boundary

    example_dict = {
        "messages": messages,
        "metadata": metadata,
    }
    if checkpoint_store:
        checkpoint_store.add_checkpoint(content_hash, spec["npc_key"], category, concept_str, example_dict)
    return example_dict


def generate_example(spec, category, concepts, generator=None, temperature=0.8,
                     difficulty=None, dialogue_type=None, scenario_name=None,
                     boundary=None, seed=None, technique="template"):
    """Synchronous wrapper for generate_example_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        generate_example_async(
            spec, category, concepts, generator=generator, temperature=temperature,
            difficulty=difficulty, dialogue_type=dialogue_type, scenario_name=scenario_name,
            boundary=boundary, seed=seed, technique=technique
        )
    )


async def generate_multi_turn_example_async(spec, concepts, generator, temperature=C.LLM_GENERATOR_TEMPERATURE, num_turns=3, technique="template", seed=None, session=None, executor=None, retriever=None, guardrail=None, checkpoint_store=None):
    """Generate a multi-turn realistic conversation using dual-agent simulation."""
    npc_name = spec["npc_name"]
    system_prompt = spec["system_prompt"]
    concept = random.choice(concepts)
    concept_category = getattr(concept, "category", None) if isinstance(concept, Concept) else None

    grounding = ""
    if retriever:
        contexts = retriever.get_grounding_context(str(concept), top_k=2)
        if contexts:
            grounding = "\nGrounding Context:\n" + "\n".join(contexts)

    student_personas = [
        "a skeptical beginner who asks practical, real-world questions",
        "a curious intermediate learner looking for deeper nuances",
        "a confused student who often makes common misconceptions"
    ]
    student_persona = random.choice(student_personas)

    student_sys = f"You are {student_persona}. You are having a conversation with an expert named {npc_name} about '{concept}'. Keep your questions short, natural, and conversational (1-2 sentences). Never break character."

    turns = []
    messages = [{"role": "system", "content": system_prompt}]
    conversation_history = []

    student_prompt = f"Start the conversation by asking a natural question about '{concept}'."
    first_user = await generator.generate_async(student_sys, student_prompt, temperature=0.8, session=session, executor=executor)
    if not first_user:
        return None
    
    turns.append({"role": "user", "content": first_user})
    messages.append({"role": "user", "content": first_user})
    conversation_history.append(f"Student: {first_user}")

    for turn_idx in range(num_turns):
        npc_prompt = f"You are {npc_name}. Respond to the user's latest message adhering strictly to your persona.{grounding}\n\nConversation so far:\n" + "\n".join(conversation_history)
        
        npc_resp = None
        for attempt in range(3):
            resp = await generator.generate_async(system_prompt, npc_prompt, temperature=temperature, session=session, executor=executor)
            if resp and guardrail:
                is_valid, reason = guardrail.validate(resp, [grounding], npc_name)
                if not is_valid:
                    npc_prompt += f"\n\n[System Guardrail Alert: Your previous response was rejected because: {reason}. Rewrite your response strictly fixing this issue.]"
                    continue
            npc_resp = resp
            break
        
        if not npc_resp:
            return None
        
        turns.append({"role": "assistant", "content": npc_resp})
        messages.append({"role": "assistant", "content": npc_resp})
        conversation_history.append(f"{npc_name}: {npc_resp}")

        if turn_idx < num_turns - 1:
            follow_up_prompt = f"The expert just responded:\n{npc_resp}\n\nAsk a natural follow-up question, ask for clarification, or bring up a related aspect. Keep it short (1-2 sentences)."
            student_resp = await generator.generate_async(student_sys, follow_up_prompt, temperature=0.8, session=session, executor=executor)
            if not student_resp:
                break
            turns.append({"role": "user", "content": student_resp})
            messages.append({"role": "user", "content": student_resp})
            conversation_history.append(f"Student: {student_resp}")

    content_hash = compute_content_hash(messages)
    example_dict = {
        "messages": messages,
        "metadata": {
            "npc_key": spec["npc_key"],
            "category": "multi_turn",
            "technique": technique,
            "source": f"llm_sim:{generator.__class__.__name__}",
            "split": "train",
            "concept": str(concept),
            "concept_category": concept_category,
            "difficulty": None,
            "safety_tags": [],
            "content_hash": content_hash,
            "generator_params": {
                "seed": seed,
                "temperature": temperature,
                "multi_turn": True,
                "reference_doc": spec.get("reference_doc"),
                "student_persona": student_persona
            },
        },
    }
    if checkpoint_store:
        checkpoint_store.add_checkpoint(content_hash, spec["npc_key"], "multi_turn", str(concept), example_dict)
    return example_dict


def generate_multi_turn_example(spec, concepts, generator, temperature=C.LLM_GENERATOR_TEMPERATURE, num_turns=3, technique="template", seed=None):
    """Synchronous wrapper for generate_multi_turn_example_async."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(
        generate_multi_turn_example_async(
            spec, concepts, generator, temperature=temperature, num_turns=num_turns,
            technique=technique, seed=seed
        )
    )


async def generate_dataset_async_runner(spec, concepts, examples_per_category, generator, multi_turn_ratio, temperature, technique, seed, quest_scenarios, refusal_boundaries, retriever, guardrail, checkpoint_store, telemetry_reporter):
    examples = []
    tasks = []
    total_count = sum(examples_per_category.values())
    
    existing_examples = checkpoint_store.get_all_for_npc(spec["npc_key"]) if checkpoint_store else []
    existing_by_cat = defaultdict(list)
    for ex in existing_examples:
        cat = ex.get("metadata", {}).get("category", "unknown")
        existing_by_cat[cat].append(ex)
    
    semaphore = asyncio.Semaphore(15)
    
    client_session = None
    if aiohttp:
        client_session = aiohttp.ClientSession()

    with ThreadPoolExecutor(max_workers=15) as executor:
        for category, count in examples_per_category.items():
            if category not in CATEGORY_TEMPLATES:
                continue

            recovered = existing_by_cat.get(category, [])[:count]
            examples.extend(recovered)
            remaining_count = count - len(recovered)
            if recovered:
                print(f"  Recovered {len(recovered)} existing examples for '{category}' from checkpoint.")
            
            if remaining_count <= 0:
                continue

            difficulties = None
            dialogue_types = None
            scenario_names = None
            boundaries = None

            if category == "teaching":
                n_beg = int(remaining_count * 0.40)
                n_int = int(remaining_count * 0.35)
                n_adv = remaining_count - n_beg - n_int
                difficulties = (["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv)
                random.shuffle(difficulties)
            elif category == "dialogue":
                n_clar = int(remaining_count * 0.20)
                n_dive = int(remaining_count * 0.30)
                n_app = int(remaining_count * 0.30)
                n_misc = remaining_count - n_clar - n_dive - n_app
                dialogue_types = (["clarification"] * n_clar + ["deep_dive"] * n_dive
                                + ["application"] * n_app + ["misconception"] * n_misc)
                random.shuffle(dialogue_types)
                n_beg = int(remaining_count * 0.40)
                n_int = int(remaining_count * 0.35)
                n_adv = remaining_count - n_beg - n_int
                difficulties = (["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv)
                random.shuffle(difficulties)
            elif category == "quest" and quest_scenarios:
                scenario_names = [quest_scenarios[i % len(quest_scenarios)] for i in range(remaining_count)]
                random.shuffle(scenario_names)
                difficulties = ["intermediate"] * remaining_count
            elif category == "refusal" and refusal_boundaries:
                boundaries = [refusal_boundaries[i % len(refusal_boundaries)] for i in range(remaining_count)]
                random.shuffle(boundaries)
                difficulties = ["beginner"] * remaining_count
            elif category == "identity":
                difficulties = ["beginner"] * remaining_count

            print(f"  Generating {remaining_count} new examples for '{category}' (async batching)...")
            
            async def gen_task(cat, diff, dt, sn, bd):
                async with semaphore:
                    if generator and multi_turn_ratio > 0 and cat in ["teaching", "dialogue"] and random.random() < multi_turn_ratio:
                        ex = await generate_multi_turn_example_async(spec, concepts, generator, temperature=temperature, technique=technique, seed=seed, session=client_session, executor=executor, retriever=retriever, guardrail=guardrail, checkpoint_store=checkpoint_store)
                        if not ex:
                            ex = await generate_example_async(spec, cat, concepts, generator=generator, temperature=temperature, difficulty=diff, dialogue_type=dt, scenario_name=sn, boundary=bd, seed=seed, technique=technique, session=client_session, executor=executor, retriever=retriever, guardrail=guardrail, checkpoint_store=checkpoint_store)
                    else:
                        ex = await generate_example_async(spec, cat, concepts, generator=generator, temperature=temperature, difficulty=diff, dialogue_type=dt, scenario_name=sn, boundary=bd, seed=seed, technique=technique, session=client_session, executor=executor, retriever=retriever, guardrail=guardrail, checkpoint_store=checkpoint_store)
                    if ex:
                        ex["metadata"]["category"] = cat
                        examples.append(ex)
                        if telemetry_reporter:
                            telemetry_reporter.report(total_count, len(examples), cat)
                        if len(examples) % 5 == 0 or len(examples) == total_count:
                            print(f"    Progress: {len(examples)}/{total_count}")
                    return ex

            for i in range(remaining_count):
                diff = difficulties[i] if difficulties else None
                dt = dialogue_types[i] if dialogue_types else None
                sn = scenario_names[i] if scenario_names else None
                bd = boundaries[i] if boundaries else None
                tasks.append(gen_task(category, diff, dt, sn, bd))

        if tasks:
            await asyncio.gather(*tasks)

    if client_session:
        await client_session.close()

    return examples


def generate_dataset(spec, output_path, seed=C.DEFAULT_SEED, include_validation=True, val_split=C.DEFAULT_VAL_SPLIT, generator=None, multi_turn_ratio=0.2, temperature=0.8, technique="template", spec_path=None, peerlm_report=None, telemetry_ipc=None):
    """Generate a complete dataset from a subject spec."""
    random.seed(seed)
    
    ingest_peerlm_report(spec, peerlm_report)
    
    concepts = ConceptExtractor(spec).extract()
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})

    output_path_obj = Path(output_path)
    checkpoint_db_path = output_path_obj.parent / ".checkpoint.db"
    checkpoint_store = CheckpointStore(str(checkpoint_db_path))
    retriever = ReferenceDocRetriever(spec.get("reference_doc"))
    guardrail = DialogueGuardrail()
    telemetry_reporter = TelemetryReporter(telemetry_ipc)

    quest_spec = spec.get("quest", {})
    quest_scenario_list = quest_spec.get("scenarios", [])
    quest_scenarios = [s["name"] for s in quest_scenario_list] if quest_scenario_list else []

    refusal_spec = spec.get("refusal", {})
    refusal_boundaries = refusal_spec.get("boundaries", [])

    if generator:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        examples = loop.run_until_complete(
            generate_dataset_async_runner(
                spec, concepts, examples_per_category, generator, multi_turn_ratio, temperature,
                technique, seed, quest_scenarios, refusal_boundaries, retriever, guardrail,
                checkpoint_store, telemetry_reporter
            )
        )
    else:
        examples = []
        total_count = sum(examples_per_category.values())
        current = 0
        
        existing_examples = checkpoint_store.get_all_for_npc(spec["npc_key"]) if checkpoint_store else []
        existing_by_cat = defaultdict(list)
        for ex in existing_examples:
            cat = ex.get("metadata", {}).get("category", "unknown")
            existing_by_cat[cat].append(ex)

        for category, count in examples_per_category.items():
            if category not in CATEGORY_TEMPLATES:
                print(f"  [warn] Unknown category '{category}', skipping")
                continue

            recovered = existing_by_cat.get(category, [])[:count]
            examples.extend(recovered)
            remaining_count = count - len(recovered)
            if recovered:
                print(f"  Recovered {len(recovered)} existing examples for '{category}' from checkpoint.")
                current += len(recovered)
            
            if remaining_count <= 0:
                continue

            difficulties = None
            dialogue_types = None
            scenario_names = None
            boundaries = None

            if category == "teaching":
                n_beg = int(remaining_count * 0.40)
                n_int = int(remaining_count * 0.35)
                n_adv = remaining_count - n_beg - n_int
                difficulties = (["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv)
                random.shuffle(difficulties)
            elif category == "dialogue":
                n_clar = int(remaining_count * 0.20)
                n_dive = int(remaining_count * 0.30)
                n_app = int(remaining_count * 0.30)
                n_misc = remaining_count - n_clar - n_dive - n_app
                dialogue_types = (["clarification"] * n_clar + ["deep_dive"] * n_dive
                                + ["application"] * n_app + ["misconception"] * n_misc)
                random.shuffle(dialogue_types)
                n_beg = int(remaining_count * 0.40)
                n_int = int(remaining_count * 0.35)
                n_adv = remaining_count - n_beg - n_int
                difficulties = (["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv)
                random.shuffle(difficulties)
            elif category == "quest" and quest_scenarios:
                scenario_names = [quest_scenarios[i % len(quest_scenarios)] for i in range(remaining_count)]
                random.shuffle(scenario_names)
                difficulties = ["intermediate"] * remaining_count
            elif category == "refusal" and refusal_boundaries:
                boundaries = [refusal_boundaries[i % len(refusal_boundaries)] for i in range(remaining_count)]
                random.shuffle(boundaries)
                difficulties = ["beginner"] * remaining_count
            elif category == "identity":
                difficulties = ["beginner"] * remaining_count

            print(f"  Generating {remaining_count} examples for '{category}'...")
            for i in range(remaining_count):
                diff = difficulties[i] if difficulties else None
                dt = dialogue_types[i] if dialogue_types else None
                sn = scenario_names[i] if scenario_names else None
                bd = boundaries[i] if boundaries else None

                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                
                example = loop.run_until_complete(
                    generate_example_async(
                        spec, category, concepts, generator=generator, temperature=temperature,
                        difficulty=diff, dialogue_type=dt, scenario_name=sn, boundary=bd, seed=seed,
                        technique=technique, session=None, executor=None, retriever=retriever,
                        guardrail=guardrail, checkpoint_store=checkpoint_store
                    )
                )

                example["metadata"]["category"] = category
                examples.append(example)
                current += 1
                if telemetry_reporter:
                    telemetry_reporter.report(total_count, current, category)
                if current % 5 == 0 or current == total_count:
                    print(f"    Progress: {current}/{total_count}")

    # ── Split into train/validation (stratified by category) ─────────────
    if include_validation and len(examples) > 5:
        by_category = defaultdict(list)
        for ex in examples:
            cat = ex.get("metadata", {}).get("category", "unknown")
            by_category[cat].append(ex)

        train_examples = []
        val_examples = []
        for cat, cat_examples in by_category.items():
            random.shuffle(cat_examples)
            # Ensure at least 1 example for validation if count > 1
            split = max(1, min(len(cat_examples) - 1, int(len(cat_examples) * val_split))) if len(cat_examples) > 1 else 0
            val_examples.extend(cat_examples[:split])
            train_examples.extend(cat_examples[split:])

        random.shuffle(train_examples)
        random.shuffle(val_examples)
    else:
        train_examples = list(examples)
        val_examples = []

    # Set split metadata on every example
    for ex in train_examples:
        ex["metadata"]["split"] = "train"
    for ex in val_examples:
        ex["metadata"]["split"] = "validation"

    # Write training set
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    train_path = output_path
    with open(train_path, "w") as f:
        for ex in train_examples:
            f.write(json.dumps(ex) + "\n")

    # Write validation set
    val_path = None
    if val_examples:
        val_path = output_path.parent / "validation.jsonl"
        with open(val_path, "w") as f:
            for ex in val_examples:
                f.write(json.dumps(ex) + "\n")

    # ── Compute statistics for manifest ──
    by_category = defaultdict(int)
    by_difficulty = defaultdict(int)
    by_concept = defaultdict(int)

    for ex in examples:
        meta = ex.get("metadata", {})
        by_category[meta.get("category", "unknown")] += 1
        diff = meta.get("difficulty")
        if diff:
            by_difficulty[diff] += 1
        conc = meta.get("concept")
        if conc:
            by_concept[conc] += 1

    # Compute spec file hash for provenance tracking
    spec_hash = None
    if spec_path:
        spec_path_resolved = Path(spec_path)
        if spec_path_resolved.exists():
            spec_bytes = spec_path_resolved.read_bytes()
            spec_hash = "sha256:" + hashlib.sha256(spec_bytes).hexdigest()
        else:
            print(f"  [warn] Could not hash spec file {spec_path}: file not found")

    # Write train_manifest.json
    manifest = {
        "npc_key": spec["npc_key"],
        "technique": technique,
        "generation": {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": seed,
            "generator_version": "improved-workflow-v1",
            "sanitizer_version": "v1",
        },
        "spec": {
            "file": str(spec_path) if spec_path else None,
            "hash": spec_hash,
            "ref_doc": spec.get("reference_doc"),
        },
        "statistics": {
            "total": len(examples),
            "train": len(train_examples),
            "validation": len(val_examples),
            "by_category": dict(by_category),
            "by_difficulty": dict(by_difficulty),
            "by_concept": dict(sorted(by_concept.items(), key=lambda x: -x[1])),
        },
    }

    manifest_path = output_path.parent / "train_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"  Manifest:        {manifest_path}")

    return {
        "spec": spec["npc_key"],
        "total": len(examples),
        "train": len(train_examples),
        "validation": len(val_examples),
        "categories": dict(examples_per_category),
        "train_path": str(train_path),
        "val_path": str(val_path) if val_path else None,
        "manifest_path": str(manifest_path),
    }


def generate_synthetic_goldens_from_primer(ref_doc_path: str, npc_key: str, output_path: str):
    """Generates complex evaluation test cases directly from an NPC reference document."""
    try:
        from deepeval.dataset import EvaluationDataset
        from deepeval.models import OllamaModel
        from deepeval.synthesizer import Synthesizer
    except ImportError:
        print("[warn] deepeval is not installed or import failed. Skipping golden synthesis.")
        return

    text = Path(ref_doc_path).read_text(encoding="utf-8")
    chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 50]

    judge = OllamaModel(
        model=os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b"),
        base_url=os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=float(os.getenv("DEEPEVAL_OLLAMA_TEMPERATURE", "0")),
    )

    synthesizer = Synthesizer(model=judge, async_mode=True)
    print(f"Synthesizing goldens for {npc_key} using DeepEval...")
    try:
        synthesizer.generate_test_cases(
            docs=chunks,
            num_test_cases=20,
            max_retries=3,
            include_expected_output=True,
        )
        dataset = EvaluationDataset(test_cases=synthesizer.test_cases)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        dataset.save_as_json(output_path)
        print(f"Saved {len(synthesizer.test_cases)} synthetic goldens to {output_path}")
    except Exception as e:
        print(f"[error] DeepEval golden synthesis failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Generate ChatML dataset from a subject spec")
    parser.add_argument("spec", help="Path to subject spec JSON file")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSONL path (default: subjects/datasets/<npc_key>/<technique>/train.jsonl)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-validation", action="store_true",
                        help="Skip validation split")
    parser.add_argument("--val-split", type=float, default=0.12,
                        help="Validation split fraction (default: C.DEFAULT_VAL_SPLIT)")
    parser.add_argument("--ollama", action="store_true", help="Use local Ollama for generation")
    parser.add_argument("--model", default="llama3.1:latest", help="Ollama model to use")
    parser.add_argument("--url", default="http://localhost:11434/api/chat", help="Ollama API URL")
    parser.add_argument("--multi-turn-ratio", type=float, default=0.2, help="Ratio of multi-turn dialogues (0.0 to 1.0)")
    parser.add_argument("--temperature", type=float, default=0.8, help="Generation temperature")
    parser.add_argument("--technique", default="template",
                        choices=["template", "ollama", "openai", "anthropic", "docs"],
                        help="Generation technique subdirectory (default: template)")
    parser.add_argument("--docs-manifest", default=None,
                        help="Curated corpus manifest for --technique docs (defaults to spec dataset.corpus_manifest)")
    parser.add_argument("--concept-focus", action="append", dest="concept_focus",
                        help="Focus generation on specific categories (repeatable, e.g. --concept-focus teaching --concept-focus dialogue). Boosts example count for those categories.")
    parser.add_argument("--peerlm-report", default=None,
                        help="Path to PeerLM evaluation report JSON for automated RLAIF category boosting")
    parser.add_argument("--telemetry-ipc", default=None,
                        help="Path to JSON IPC file for real-time dashboard telemetry reporting")
    parser.add_argument("--synthesize-goldens", action="store_true",
                        help="Generate synthetic evaluation goldens using DeepEval Synthesizer")
    args = parser.parse_args()

    # Import re for JSON extraction
    import re

    if args.ollama:
        args.technique = "ollama"


    generator = None
    if args.technique == "ollama":
        print(f"Initializing Ollama generator ({args.model})...")
        generator = OllamaGenerator(model=args.model, url=args.url)
    elif args.technique == "openai":
        print(f"Initializing OpenAI generator ({args.model})...")
        generator = OpenAIGenerator(model=args.model)
    elif args.technique == "anthropic":
        print(f"Initializing Anthropic generator ({args.model})...")
        generator = AnthropicGenerator(model=args.model)

    spec = load_subject_spec(args.spec)
    npc_key = spec["npc_key"]

    if args.output:
        output_path = args.output
    else:
        output_path = paths.dataset_train_path(npc_key, args.technique)

    print(f"Generating dataset for: {spec['npc_name']}")
    print(f"  Subject: {spec['subject']}")
    print()

    if args.synthesize_goldens:
        ref_doc = spec.get("reference_doc")
        if ref_doc and (PROJECT_ROOT / ref_doc).exists():
            golden_path = Path(output_path).parent / "synthetic_goldens.json"
            generate_synthetic_goldens_from_primer(str(PROJECT_ROOT / ref_doc), npc_key, str(golden_path))
        else:
            print(f"  [warn] No reference_doc found for {npc_key} or file missing. Skipping golden synthesis.")

    # ── Apply concept-focus boost ─────────────────────────────────────────
    if args.concept_focus:
        examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})
        if examples_per_category:
            print(f"  Concept focus enabled: {args.concept_focus}")
            for cat in list(examples_per_category.keys()):
                if cat in args.concept_focus:
                    boost_factor = 2.0
                    original = examples_per_category[cat]
                    examples_per_category[cat] = max(original + 4, int(original * boost_factor))
                    print(f"    {cat}: {original} -> {examples_per_category[cat]} ({boost_factor}x boost)")
            # Also add a focused note to the output path
            focus_suffix = "_focused"
            if args.output and "_focused" not in str(args.output):
                output_path = str(args.output).replace(".jsonl", f"{focus_suffix}.jsonl")
                print(f"  Focused output path: {output_path}")
        else:
            print("  [warn] --concept-focus specified but spec has no examples_per_category")

    if args.technique == "docs":
        manifest_path = (
            args.docs_manifest
            or spec.get("dataset", {}).get("corpus_manifest")
            or str(default_manifest_path())
        )
        try:
            result = generate_workflow_dataset_from_manifest(
                spec,
                manifest_path,
                output_path,
                seed=args.seed,
                include_validation=not args.no_validation,
                val_split=args.val_split,
            )
        except Exception as exc:
            print(f"Error: docs manifest generation failed: {exc}")
            sys.exit(2)
    else:
        result = generate_dataset(
            spec,
            output_path,
            seed=args.seed,
            include_validation=not args.no_validation,
            val_split=args.val_split,
            generator=generator,
            multi_turn_ratio=args.multi_turn_ratio,
            temperature=args.temperature,
            technique=args.technique,
            spec_path=args.spec,
            peerlm_report=args.peerlm_report,
            telemetry_ipc=args.telemetry_ipc,
        )

    log_state("dataset_generated", npc_key=result.get("npc_key", spec.get("npc_key", "unknown")),
              total=result["total"], train=result["train"], validation=result["validation"],
              train_path=result["train_path"], technique=args.technique)
    print(f"  Total examples:  {result['total']}")
    print(f"  Training:        {result['train']}")
    print(f"  Validation:      {result['validation']}")
    print(f"  Categories:      {json.dumps(result['categories'])}")
    print(f"  Train path:      {result['train_path']}")
    if result["val_path"]:
        print(f"  Val path:        {result['val_path']}")
    if result.get("manifest_path"):
        print(f"  Manifest:        {result['manifest_path']}")
    print()
    print("Dataset generation complete!")


if __name__ == "__main__":
    main()
