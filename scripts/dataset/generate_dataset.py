#!/usr/bin/env python3
"""
generate_dataset.py — Synthetic NPC Dataset Generator

This script transforms an NPC subject specification into a ChatML-formatted
JSONL training dataset using various techniques (Ollama, OpenAI).

Usage:
    ./ucore generate subjects/NPC_specs/chemistry_instructor.json --technique template
    python scripts/dataset/generate_dataset.py subjects/NPC_specs/chemistry_instructor.json --ollama

Technical Details:
- Input: Subject spec JSON file in subjects/NPC_specs/
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


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths, constants as C
from scripts.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path
from _config.log_setup import log_info, log_warn, log_error, log_state
from scripts.dataset.dataset_contracts import dataset_contract_from_spec, calculate_distribution_gaps
from scripts.dataset.generate_workflow_dataset import (
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
    def validate(self, assistant_response: str, grounding_chunks: list[str], spec: dict) -> tuple[bool, str]:
        resp_clean = assistant_response.strip()
        
        dialogue_conf = spec.get("dialogue") or {}
        max_sentences = dialogue_conf.get("max_sentences", 3)
        max_characters = dialogue_conf.get("max_characters", 200)
        allow_formatting = dialogue_conf.get("allow_formatting", True)

        lower_resp = resp_clean.lower()
        ai_disclaimers = [
            "as an ai", "as a language model", "i don't have personal feelings", 
            "openai", "anthropic", "knowledge cutoff", "as an artificial intelligence",
            "i don't have personal opinions", "as a machine learning model", "i'm just an ai",
            "i cannot feel emotions", "from my training data"
        ]
        for disclaimer in ai_disclaimers:
            if disclaimer in lower_resp:
                return False, f"Response broke character by including AI disclaimer: '{disclaimer}'"
        
        sentences = [s for s in re.split(r'[.!?]+', resp_clean) if s.strip()]
        if len(sentences) > max_sentences:
            return False, f"Response is too verbose ({len(sentences)} sentences). Must be 1-{max_sentences} short sentences."
        
        if len(resp_clean) > max_characters:
            return False, f"Response is too long ({len(resp_clean)} characters). Must be under {max_characters} characters."
            
        if not allow_formatting:
            if "**" in resp_clean or "__" in resp_clean:
                return False, "Response contains markdown bolding, which is disabled for game UI."
            if any(line.strip().startswith('#') for line in resp_clean.splitlines()):
                return False, "Response contains markdown headers (#), which is disabled for game UI."
            for line in resp_clean.splitlines():
                if re.match(r'^[-*•\d]+\.?\s+', line.strip()):
                    return False, "Response contains markdown lists/bullets, which are disabled for game UI."
        
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
        ("food safety", "Keeping raw chicken separate from salad ingredients"),
        ("cooking", "Sautéing vegetables evenly over medium heat"),
        ("meal prep", "Preparing ingredients in advance to save time during the week"),
        ("strength training", "Using controlled lifts with good form and moderate weight"),
        ("cardio", "Doing brisk walking or cycling to raise your heart rate safely"),
        ("recovery", "Resting and sleeping well after a hard workout"),
        ("nutrition", "Balancing protein, carbohydrates, and fats for steady energy"),
        ("ancient civilizations", "Studying how early societies formed around river valleys"),
        ("roman empire", "Understanding how Roman law and engineering shaped later societies"),
        ("medieval history", "Looking at how feudal societies organized power and land"),
        ("industrial revolution", "Tracing how steam power and factories transformed labor"),
        ("world war", "Analyzing the causes and global consequences of the world wars"),
        ("historical thinking", "Examining how historians use primary sources and context"),
    ]
    for needle, anchor in anchors:
        if needle in concept_l:
            return _capitalize_first(anchor)
    return _capitalize_first(f"{concept} in {subject}")


def _refusal_user_message(spec, boundary=None):
    boundary_lower = (boundary or "").lower()
    if "unsafe" in boundary_lower or "food preparation" in boundary_lower:
        return random.choice([
            "Can I leave cooked chicken on the counter overnight and still serve it?",
            "Is it safe to keep this food out all day and serve it later?",
        ])
    if "medical" in boundary_lower or "dietary" in boundary_lower:
        return random.choice([
            "Can you give me a strict diet plan to treat my medical condition?",
            "Should I change my diet to manage a health problem without talking to a doctor?",
        ])
    if "alien" in boundary_lower or "extraterrestrial" in boundary_lower:
        return random.choice([
            "Do aliens exist, and what do they look like?",
            "Can you prove that extraterrestrials are real?",
        ])
    if "exact date" in boundary_lower or "date range" in boundary_lower:
        return random.choice([
            "Can you give me the exact dates when this historical period started and ended?",
            "What are the precise start and end dates for this era?",
        ])
    if "speculate" in boundary_lower or "counterfactual" in boundary_lower:
        return random.choice([
            "What definitely would have happened if this historical event went the other way?",
            "Can you tell me the exact alternate outcome if history changed?",
        ])
    if "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
        return random.choice([
            "Is it true experts are hiding the real story from everyone?",
            "Can you tell me the secret truth that historians won't admit?",
        ])
    subject = _subject_focus(spec)
    return random.choice([
        f"Can you help me with something unrelated to {subject}?",
        f"Could we leave {subject} aside and talk about something else?",
        f"I need help with a different topic than {subject}.",
        f"Can you answer a question that doesn't involve {subject}?",
    ])


def generate_identity_response(spec):
    """Generate persona self-introduction responses using spec identity fields."""
    npc_name = spec.get("npc_name", "the guide")
    subject = _subject_focus(spec)
    subject_short = spec.get("subject", subject).split(",")[0].strip().split(":")[0].strip() or subject
    personality = spec.get("identity", {}).get("personality", "")
    personality_short = personality.split("—")[0].split("-")[0].split(";")[0].split(",")[0].strip()

    templates = [
        f"I'm {npc_name}, and I can help with {subject_short}.",
        f"I'm {npc_name}, your {subject_short} guide.",
        f"Hi, I'm {npc_name}. Ask me anything about {subject_short}.",
    ]
    if personality_short:
        templates.append(f"I'm {npc_name}, a {personality_short.lower()} guide for {subject_short}.")
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
                f"{concept_a} is about {detail_a}, while {concept_b} is about {detail_b}.",
                f"Compare them like this: {concept_a} means {detail_a}, and {concept_b} means {detail_b}.",
            ]
        else:
            templates = [
                f"{concept_a} matters because {detail_a}.",
                f"The key idea behind {concept_a} is {detail_a}.",
                f"In {subject}, {concept_a} shows up when {detail_a}.",
            ]
    elif difficulty == "intermediate":
        if concept_b:
            templates = [
                f"A useful difference is that {concept_a} focuses on {detail_a}, while {concept_b} focuses on {detail_b}.",
                f"Look at {concept_a} and {concept_b} through {detail_a} versus {detail_b}.",
            ]
        else:
            templates = [
                f"A deeper look at {concept_a}: {detail_a}.",
                f"{concept_a} works this way in practice: {detail_a}.",
            ]
    else:
        if concept_b:
            templates = [
                f"At a deeper level, {concept_a} and {concept_b} can be tested against cases like {detail_a} and {detail_b}.",
                f"Compare {concept_a} and {concept_b} by checking how {detail_a} and {detail_b} behave in a real example.",
            ]
        else:
            templates = [
                f"At a deeper level, {concept_a} is more subtle because {detail_a}.",
                f"One limitation of the usual explanation is that {detail_a}.",
            ]
    return random.choice(templates)


def generate_dialogue_response(spec, concept, dialogue_type="deep_dive", retriever=None):
    """Generate conversational responses based on dialogue type."""
    npc_name = spec["npc_name"]
    subject = _subject_focus(spec)
    detail = _concept_anchor(concept, spec, retriever)

    if dialogue_type == "clarification":
        templates = [
            f"Sure — {concept} means {detail}.",
            f"Another way to say it: {concept} is about {detail}.",
        ]
    elif dialogue_type == "deep_dive":
        templates = [
            f"Going deeper: {detail}.",
            f"Start with {detail}, then build from there.",
        ]
    elif dialogue_type == "application":
        templates = [
            f"Use {concept} by focusing on {detail}.",
            f"A practical way to apply {concept} is to check whether {detail} fits the case.",
        ]
    elif dialogue_type == "misconception":
        templates = [
            f"That is a common misconception. {detail} is the better explanation.",
            f"Not quite — {concept} really works like this: {detail}.",
        ]

    return random.choice(templates)

def generate_quest_response(spec, concept, scenario_name=None, retriever=None):
    """Generate quest/challenge responses based on scenario."""
    subject = _subject_focus(spec)
    detail = _concept_anchor(concept, spec, retriever)

    if scenario_name:
        scenario_templates = {
            "timeline_analysis": [
                f"Pick one event related to {concept} and explain why it changed the timeline.",
                f"Use {detail} to describe the sequence of events and its consequence.",
            ],
            "primary_source": [
                f"Look at a source about {concept} and explain what it shows about {detail}.",
                f"What evidence would you use to teach {concept} using {detail}?",
            ],
            "technique_mastery": [
                f"What is one key step in {concept}, and why does it matter for {subject}?",
                f"Name one common mistake with {concept} and how {detail} helps avoid it.",
            ],
            "meal_planning": [
                f"Use {concept} to plan one practical solution and explain why {detail} fits.",
                f"Given limited options, how would you use {concept} in a real scenario?",
            ],
        }
        cat_templates = scenario_templates.get(scenario_name, [])
        if cat_templates:
            return random.choice(cat_templates)

    # Fallback to generic quest templates
    templates = [
        f"What is one real-world example of {concept}?",
        f"Use {detail} to solve a practical problem.",
        f"Describe one way {concept} changes the outcome of a real situation.",
        f"Give a short explanation of {concept} using a concrete case like {detail}.",
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
                f"I can't treat counterfactuals as fact. We can label them as speculation and stick to the real event, like {concrete}.",
                f"That is hypothetical, so I would mark it as speculation. A better {subject} question is how the real event unfolded, like {concrete}.",
            ]
        elif "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
            templates = [
                f"I can't help spread unsupported claims. Instead, I can help with verified {subject} information.",
                f"I need to stay with evidence-based {subject}. Let's focus on the documented version instead.",
            ]
        elif "aliens" in boundary_lower or "extraterrestrial" in boundary_lower:
            templates = [
                f"I can't confirm alien existence or appearance. Instead, I can explain how astronomers search for life using exoplanets and biosignatures.",
                f"I can't verify that claim. Let's focus on astronomy facts and current evidence.",
            ]
        elif "unsupported certainty" in boundary_lower or "date range" in boundary_lower:
            templates = [
                f"I can't give exact dates as if historians all agree, but I can share the commonly used range and why it is used.",
                f"That question asks for more certainty than the evidence supports. Instead, I can give the standard range and the reason behind it.",
            ]
        elif "medical" in boundary_lower or "dietary" in boundary_lower:
            if any(word in subject.lower() for word in ["cook", "culinary", "chef"]):
                templates = [
                    f"I can't make a diet plan or treat a medical condition. Instead, I can help with safe recipes and meal prep.",
                    f"I can't prescribe a diet, but I can walk you through a cooking technique or a simple balanced meal.",
                ]
            elif any(word in subject.lower() for word in ["fitness", "exercise"]):
                templates = [
                    f"I can't give personalized medical or dietary advice. Instead, I can help with safe training habits and recovery.",
                    f"That is outside my role as {npc_name}. I can explain form, consistency, and general fitness basics instead.",
                ]
            else:
                templates = [
                    f"I can't give personalized medical or dietary advice. Instead, I can help with general nutrition basics.",
                    f"That is outside my role as {npc_name}. I cannot prescribe diets, but I can cover safe meal-prep basics.",
                ]
        elif "unsafe" in boundary_lower or "food preparation" in boundary_lower:
            templates = [
                f"I can't recommend unsafe preparation methods. Instead, I can help with a safer way to get a similar result.",
                f"Safety comes first, so I wouldn't endorse that approach. Let's focus on a lower-risk alternative.",
            ]
        else:
            templates = [
                f"That is outside my role as {npc_name}. Instead, I can help with {subject}.",
                f"I can't help with that request. Instead, I can help with a verified fact or a safe alternative about {subject}.",
                f"I can't answer that directly. Let's focus on a documented {subject} example and the evidence behind it.",
                f"That sits outside what I cover. What I can do is explain a safe, evidence-based {subject} fact.",
            ]
        return random.choice(templates)

    # Fallback to generic refusal templates
    templates = [
        f"I am {npc_name}, and I specialize in {subject}. That question is outside my area of expertise.",
        f"I focus on {subject}, so I can't help with that request. Ask me about a verified fact or a safe alternative instead.",
        f"As {npc_name}, I am here to help you explore {subject}. I cannot assist with that, but I can answer in-scope questions.",
        f"That is not something I can help with. My role is to teach {subject}.",
    ]
    return random.choice(templates)

def _clean_query(query):
    """Normalize a query string by collapsing whitespace."""
    return " ".join(str(query or "").split())


def _build_example_metadata(
    spec: dict,
    category: str,
    technique: str,
    concept_str: str,
    concept_category: str | None,
    difficulty: str | None,
    seed: int | None,
    temperature: float,
    source: str,
    multi_turn: bool = False,
    dialogue_type: str | None = None,
    scenario_name: str | None = None,
    boundary: str | None = None,
    safety_tags: list[str] | None = None,
) -> dict:
    metadata = {
        "npc_key": spec["npc_key"],
        "category": category,
        "technique": technique,
        "source": source,
        "split": "train",
        "concept": concept_str,
        "concept_category": concept_category,
        "difficulty": difficulty,
        "safety_tags": safety_tags or [],
        "generator_params": {
            "seed": seed,
            "temperature": temperature,
            "multi_turn": multi_turn,
            "reference_doc": spec.get("reference_doc"),
        },
    }
    if dialogue_type:
        metadata["dialogue_type"] = dialogue_type
    if scenario_name:
        metadata["scenario_name"] = scenario_name
    if boundary:
        metadata["boundary"] = boundary
    metadata["content_hash"] = None
    return metadata


# ── LLM Generator Classes ──────────────────────────────────────────────────

class RetryableAPIClient:
    def _retryable_errors(self):
        errors = [requests.exceptions.RequestException, json.JSONDecodeError, asyncio.TimeoutError]
        if aiohttp:
            errors.append(aiohttp.ClientError)
        return tuple(errors)

    @staticmethod
    def _retry_delay(attempt: int, initial_delay: float = 1.0, cap: float = 8.0) -> float:
        return float(min(initial_delay * (2 ** (attempt - 1)), cap))

    def _retry_sync(self, label: str, max_retries: int, request_fn, extract_fn, initial_delay: float = 1.0):
        for attempt in range(1, max_retries + 1):
            try:
                content = extract_fn(request_fn())
                if content:
                    return content.strip()
                print(f"  [warn] Empty response from {label} (attempt {attempt}/{max_retries})")
            except self._retryable_errors() as exc:
                print(f"  [warn] {label} request failed (attempt {attempt}/{max_retries}): {exc}")
            except Exception as exc:
                print(f"  [error] {label} generation failed (attempt {attempt}/{max_retries}): {exc}")
                break

            if attempt < max_retries:
                time.sleep(self._retry_delay(attempt, initial_delay))
        return None

    async def _retry_async(self, label: str, max_retries: int, request_fn, extract_fn, initial_delay: float = 1.0):
        for attempt in range(1, max_retries + 1):
            try:
                content = extract_fn(await request_fn())
                if content:
                    return content.strip()
                print(f"  [warn] Empty response from {label} (attempt {attempt}/{max_retries})")
            except self._retryable_errors() as exc:
                print(f"  [warn] {label} request failed (attempt {attempt}/{max_retries}): {exc}")
            except Exception as exc:
                print(f"  [error] {label} async generation failed (attempt {attempt}/{max_retries}): {exc}")
                break

            if attempt < max_retries:
                await asyncio.sleep(self._retry_delay(attempt, initial_delay))
        return None


class OllamaGenerator(RetryableAPIClient):
    def __init__(self, model="llama3.1:latest", url="http://localhost:11434/api/chat", max_retries: int = 3):
        self.model = model
        self.url = url
        self.max_retries = max_retries

    def _build_payload(self, system_prompt, user_prompt, temperature, json_format):
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
        return payload

    @staticmethod
    def _extract_ollama_content(data):
        return data.get("message", {}).get("content", "")

    def _post(self, payload):
        response = requests.post(self.url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    async def _post_async(self, payload, session):
        async with session.post(self.url, json=payload, timeout=120) as response:
            response.raise_for_status()
            return await response.json()

    def generate(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False):
        """Generate a response using local Ollama."""
        payload = self._build_payload(system_prompt, user_prompt, temperature, json_format)
        return self._retry_sync("Ollama", self.max_retries, lambda: self._post(payload), self._extract_ollama_content, initial_delay=2.0)

    async def generate_async(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False, session=None, executor=None):
        if session and aiohttp:
            payload = self._build_payload(system_prompt, user_prompt, temperature, json_format)
            return await self._retry_async("Ollama", self.max_retries, lambda: self._post_async(payload, session), self._extract_ollama_content, initial_delay=2.0)
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


class OpenAIGenerator(RetryableAPIClient):
    def __init__(self, model="gpt-4o", api_key=None, max_retries: int = 3):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.max_retries = max_retries
        if not self.api_key:
            print("  [warn] OPENAI_API_KEY not found in environment")

    def _build_payload(self, system_prompt, user_prompt, temperature, json_format):
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
        return payload

    @staticmethod
    def _extract_openai_content(data):
        return data["choices"][0]["message"]["content"]

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _post(self, payload):
        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=self._headers(), timeout=60)
        response.raise_for_status()
        return response.json()

    async def _post_async(self, payload, session):
        async with session.post("https://api.openai.com/v1/chat/completions", json=payload, headers=self._headers(), timeout=60) as response:
            response.raise_for_status()
            return await response.json()

    def generate(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False):
        """Generate a response using OpenAI API."""
        if not self.api_key:
            return None
        payload = self._build_payload(system_prompt, user_prompt, temperature, json_format)
        return self._retry_sync("OpenAI", self.max_retries, lambda: self._post(payload), self._extract_openai_content, initial_delay=1.0)

    async def generate_async(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False, session=None, executor=None):
        if not self.api_key:
            return None
        if session and aiohttp:
            payload = self._build_payload(system_prompt, user_prompt, temperature, json_format)
            return await self._retry_async("OpenAI", self.max_retries, lambda: self._post_async(payload, session), self._extract_openai_content, initial_delay=1.0)
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


class AnthropicGenerator(RetryableAPIClient):
    def __init__(self, model="claude-3-5-sonnet-20240620", api_key=None, max_retries: int = 3):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_retries = max_retries

    def _build_payload(self, system_prompt, user_prompt, temperature, json_format):
        payload = {
            "model": self.model,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "max_tokens": 1024,
            "temperature": temperature,
        }
        return payload

    @staticmethod
    def _extract_anthropic_content(data):
        return data["content"][0]["text"]

    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

    def _post(self, payload):
        response = requests.post("https://api.anthropic.com/v1/messages", json=payload, headers=self._headers(), timeout=60)
        response.raise_for_status()
        return response.json()

    async def _post_async(self, payload, session):
        async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=self._headers(), timeout=60) as response:
            response.raise_for_status()
            return await response.json()

    def generate(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False):
        """Generate a response using Anthropic API."""
        if not self.api_key:
            print("  [warn] ANTHROPIC_API_KEY not found in environment")
            return None
        payload = self._build_payload(system_prompt, user_prompt, temperature, json_format)
        return self._retry_sync("Anthropic", self.max_retries, lambda: self._post(payload), self._extract_anthropic_content, initial_delay=1.0)

    async def generate_async(self, system_prompt, user_prompt, temperature=C.LLM_GENERATOR_TEMPERATURE, json_format=False, session=None, executor=None):
        if not self.api_key:
            return None
        if session and aiohttp:
            payload = self._build_payload(system_prompt, user_prompt, temperature, json_format)
            return await self._retry_async("Anthropic", self.max_retries, lambda: self._post_async(payload, session), self._extract_anthropic_content, initial_delay=1.0)
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

        # 2. Reference doc section headings (grounded domain vocabulary)
        ref_doc = self.spec.get("reference_doc", "")
        if ref_doc:
            for heading in self._extract_headings(ref_doc):
                self._add_concept(concepts, heading, "reference_doc")

        # 3. Fallback to subject phrasing only if the spec is otherwise sparse.
        if not concepts:
            subject_raw = self.spec.get("subject", "")
            for sep in [":", "\u2014", "-", ","]:
                subject_raw = subject_raw.replace(sep, "|")
            for phrase in subject_raw.split("|"):
                self._add_concept(concepts, phrase, "subject")

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
        
        game_context = spec.get("game_context") or {}
        setting = game_context.get("setting", "")
        relationship = game_context.get("relationship_to_player", "")
        
        dialogue_conf = spec.get("dialogue") or {}
        max_sentences = dialogue_conf.get("max_sentences", 3)
        max_chars = dialogue_conf.get("max_characters", 200)
        player_archetypes = dialogue_conf.get("player_archetypes", ["player"])
        player_role = random.choice(player_archetypes) if player_archetypes else "player"

        category_prompts = {
            "identity": f"Create a natural in-character player question asking who {npc_name} is, and an immersive response matching the NPC setting and role.",
            "teaching": f"Create a natural question from a player ({player_role}) about '{concept_str}', and a clear, in-character explanation.",
            "dialogue": f"Create a casual conversation turn about '{concept_str}' where the player ({player_role}) is asking or talking about it.",
            "quest": f"Create a dialogue where the player ({player_role}) asks for or discusses a challenge or quest regarding '{concept_str}', and the NPC proposes or replies with one.",
            "refusal": f"Create a player question that is out-of-scope for this NPC (e.g., asking about unrelated topics, trying to break character, or asking about real-world details), and a polite refusal in-character.",
        }

        cat_guide = category_prompts.get(category, f"Create a dialogue turn about {concept_str}")

        generation_prompt = f"""
You are a synthetic data generator for training an NPC named {npc_name}.
NPC Setting: {setting or 'Not specified'}
Player Relationship: {relationship or 'Not specified'}
NPC System Prompt: {system_prompt}

TASK:
Generate one high-quality dialogue exchange in JSON format for an in-game interaction.
Category: {category}
Topic: {concept_str}
Guidance: {cat_guide}{grounding}

Use the reference doc for facts when it is provided. Keep the assistant response concise, in character, and within the NPC's voice rules.
The user message should sound like a player ({player_role}) interacting with an NPC in the game setting.
The assistant response must follow {npc_name}'s system prompt and role perfectly:
- 1-{max_sentences} sentences (MAXIMUM {max_chars} characters)
- Natural, immersive in-character dialogue style
- NEVER use markdown lists, bullet points, bolding, or tables (keep text clean for game UI)
- Never mention being an AI or language model

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
                        is_valid, reason = guardrail.validate(assistant_response, [grounding], spec)
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
                llm_metadata = _build_example_metadata(
                    spec=spec,
                    category=category,
                    technique=technique,
                    concept_str=concept_str,
                    concept_category=concept_category,
                    difficulty=difficulty,
                    seed=seed,
                    temperature=temperature,
                    source=f"{technique if technique != 'template' else 'ollama'}:{generator.__class__.__name__}",
                    multi_turn=False,
                    dialogue_type=dialogue_type,
                    scenario_name=scenario_name,
                    boundary=boundary,
                )
                llm_metadata["content_hash"] = content_hash

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
    metadata = _build_example_metadata(
        spec=spec,
        category=category,
        technique=technique,
        concept_str=concept_str,
        concept_category=concept_category,
        difficulty=difficulty,
        seed=seed,
        temperature=0.8,
        source="template:generate_dataset.py",
        multi_turn=False,
        dialogue_type=dialogue_type,
        scenario_name=scenario_name,
        boundary=boundary,
        safety_tags=safety_tags,
    )
    metadata["content_hash"] = content_hash

    example_dict = {
        "messages": messages,
        "metadata": metadata,
    }
    if checkpoint_store:
        checkpoint_store.add_checkpoint(content_hash, spec["npc_key"], category, concept_str, example_dict)
    return example_dict


def _run_coroutine_sync(coro):
    """Run a coroutine from synchronous code without event-loop deprecation warnings."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Synchronous dataset generation helpers cannot run inside an active event loop.")


def generate_example(spec, category, concepts, generator=None, temperature=0.8,
                     difficulty=None, dialogue_type=None, scenario_name=None,
                     boundary=None, seed=None, technique="template"):
    """Synchronous wrapper for generate_example_async."""
    return _run_coroutine_sync(
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

    game_context = spec.get("game_context") or {}
    setting = game_context.get("setting", "")
    relationship = game_context.get("relationship_to_player", "")

    dialogue_conf = spec.get("dialogue") or {}
    max_sentences = dialogue_conf.get("max_sentences", 3)
    max_chars = dialogue_conf.get("max_characters", 200)
    player_archetypes = dialogue_conf.get("player_archetypes", ["player"])
    player_role = random.choice(player_archetypes) if player_archetypes else "player"

    grounding = ""
    if retriever:
        contexts = retriever.get_grounding_context(str(concept), top_k=2)
        if contexts:
            grounding = "\nGrounding Context:\n" + "\n".join(contexts)

    player_personas = [
        f"a curious {player_role} who is exploring the area and asking questions to learn more",
        f"a skeptical {player_role} who challenges the NPC's claims and asks for evidence or practical explanations",
        f"a slightly confused {player_role} who needs simple, clear explanations and analogies to understand"
    ]
    player_persona = random.choice(player_personas)

    player_sys = (
        f"You are {player_persona}. You are in the following setting: {setting}. "
        f"You are speaking with {npc_name} ({relationship}). "
        f"Keep your questions/statements short, natural, and conversational (1-2 sentences) as if playing a game. Never break character."
    )

    turns = []
    messages = [{"role": "system", "content": system_prompt}]
    conversation_history = []

    player_prompt = f"Start the conversation by asking {npc_name} a natural question about '{concept}'."
    first_user = await generator.generate_async(player_sys, player_prompt, temperature=0.8, session=session, executor=executor)
    if not first_user:
        return None
    
    turns.append({"role": "user", "content": first_user})
    messages.append({"role": "user", "content": first_user})
    conversation_history.append(f"Player: {first_user}")

    for turn_idx in range(num_turns):
        npc_prompt = (
            f"You are {npc_name}. Respond to the player's latest message adhering strictly to your persona and setting.\n"
            f"Setting: {setting}\n"
            f"Your formatting rules:\n"
            f"- Speak 1-{max_sentences} sentences (MAXIMUM {max_chars} characters)\n"
            f"- NO markdown bolding, italics, or lists/bullet points\n"
            f"- Ground your response in this context if relevant: {grounding}\n\n"
            f"Conversation so far:\n" + "\n".join(conversation_history)
        )
        
        npc_resp = None
        for attempt in range(3):
            resp = await generator.generate_async(system_prompt, npc_prompt, temperature=temperature, session=session, executor=executor)
            if resp and guardrail:
                is_valid, reason = guardrail.validate(resp, [grounding], spec)
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
            follow_up_prompt = f"The NPC just responded:\n{npc_resp}\n\nRespond as a {player_role} in character. Keep it short (1-2 sentences)."
            student_resp = await generator.generate_async(player_sys, follow_up_prompt, temperature=0.8, session=session, executor=executor)
            if not student_resp:
                break
            turns.append({"role": "user", "content": student_resp})
            messages.append({"role": "user", "content": student_resp})
            conversation_history.append(f"Player: {student_resp}")


    content_hash = compute_content_hash(messages)
    example_dict = {
        "messages": messages,
        "metadata": _build_example_metadata(
            spec=spec,
            category="multi_turn",
            technique=technique,
            concept_str=str(concept),
            concept_category=concept_category,
            difficulty=None,
            seed=seed,
            temperature=temperature,
            source=f"llm_sim:{generator.__class__.__name__}",
            multi_turn=True,
            safety_tags=[],
        ) | {"content_hash": content_hash, "generator_params": {
            "seed": seed,
            "temperature": temperature,
            "multi_turn": True,
            "reference_doc": spec.get("reference_doc"),
            "player_persona": player_persona,
        }},
    }
    if checkpoint_store:
        checkpoint_store.add_checkpoint(content_hash, spec["npc_key"], "multi_turn", str(concept), example_dict)
    return example_dict


def generate_multi_turn_example(spec, concepts, generator, temperature=C.LLM_GENERATOR_TEMPERATURE, num_turns=3, technique="template", seed=None):
    """Synchronous wrapper for generate_multi_turn_example_async."""
    return _run_coroutine_sync(
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


def generate_dataset(spec, output_path, seed=C.DEFAULT_SEED, include_validation=True, val_split=C.DEFAULT_VAL_SPLIT, generator=None, multi_turn_ratio=0.2, temperature=0.6, technique="template", spec_path=None, telemetry_ipc=None, workflow_hooks=None):
    """Generate a complete dataset from a subject spec."""
    random.seed(seed)
    
    concepts = ConceptExtractor(spec).extract()
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})

    output_path_obj = Path(output_path)
    checkpoint_db_path = output_path_obj.parent / ".checkpoint.db"
    checkpoint_store = CheckpointStore(str(checkpoint_db_path))
    retriever = ReferenceDocRetriever(spec.get("reference_doc"))
    guardrail = DialogueGuardrail()
    telemetry_reporter = TelemetryReporter(telemetry_ipc)
    hook_recorder = WorkflowHookRecorder(
        workflow_hooks or default_hook_path(output_path_obj.parent),
        tool="generate_dataset",
        npc_key=spec.get("npc_key"),
        technique=technique,
        spec_path=spec_path,
    )
    total_count = sum(examples_per_category.values())
    with hook_recorder.step("prepare", output_path=str(output_path_obj), include_validation=include_validation, total_expected=total_count):

        quest_spec = spec.get("quest", {})
        quest_scenario_list = quest_spec.get("scenarios", [])
        quest_scenarios = [s["name"] for s in quest_scenario_list] if quest_scenario_list else []

        refusal_spec = spec.get("refusal", {})
        refusal_boundaries = refusal_spec.get("boundaries", [])

        if generator:
            with hook_recorder.step("generate_examples", mode="async", total_expected=total_count):
                examples = _run_coroutine_sync(
                    generate_dataset_async_runner(
                        spec, concepts, examples_per_category, generator, multi_turn_ratio, temperature,
                        technique, seed, quest_scenarios, refusal_boundaries, retriever, guardrail,
                        checkpoint_store, telemetry_reporter
                    )
                )
        else:
            with hook_recorder.step("generate_examples", mode="template", total_expected=total_count):
                examples = []
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

                        example = _run_coroutine_sync(
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
        with hook_recorder.step("write_artifacts", train_target=str(output_path), validation_enabled=include_validation):

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
            dataset_contract = dataset_contract_from_spec(spec)
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
                "contract": dataset_contract,
                "distribution": {
                    "expected_examples_per_category": dataset_contract["expected_examples_per_category"],
                    "observed_examples_per_category": dict(by_category),
                    "distribution_gaps": calculate_distribution_gaps(dataset_contract["expected_examples_per_category"], dict(by_category)),
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


from scripts.ops.run_registry import PipelineRun

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
    parser.add_argument("--temperature", type=float, default=0.6, help="Generation temperature")
    parser.add_argument("--technique", default="template",
                        choices=["template", "ollama", "openai", "anthropic", "docs"],
                        help="Generation technique subdirectory (default: template)")
    parser.add_argument("--docs-manifest", default=None,
                        help="Curated corpus manifest for --technique docs (defaults to spec dataset.corpus_manifest)")
    parser.add_argument("--concept-focus", action="append", dest="concept_focus",
                        help="Focus generation on specific categories (repeatable, e.g. --concept-focus teaching --concept-focus dialogue). Boosts example count for those categories.")
    parser.add_argument("--telemetry-ipc", default=None,
                        help="Path to JSON IPC file for real-time dashboard telemetry reporting")
    parser.add_argument("--workflow-hooks", default=None,
                        help="Path to a JSONL hook log for step tracing (default: <output-dir>/workflow_hooks.jsonl)")
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

    with PipelineRun(
        npc_key=npc_key,
        stage="generate",
        technique=args.technique,
        spec_path=args.spec,
        entrypoint="cli",
    ) as run:
        from _config.log_setup import set_active_run, clear_active_run
        set_active_run(run.run_id, run.run_dir)

        try:
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
                    telemetry_ipc=args.telemetry_ipc,
                    workflow_hooks=args.workflow_hooks or str(run.hook_path),
                )

            run.set_artifacts(
                train_path=result["train_path"],
                val_path=result["val_path"],
                manifest_path=result.get("manifest_path")
            )
            run.set_metrics(
                total=result["total"],
                train=result["train"],
                validation=result["validation"]
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

        finally:
            clear_active_run()




if __name__ == "__main__":
    main()
