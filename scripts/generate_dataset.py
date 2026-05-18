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
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
from pathlib import Path


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


def generate_identity_response(spec):
    """Generate persona self-introduction responses using spec identity fields."""
    identity = spec.get("identity", {})
    personality = identity.get("personality", "") or ""
    background = identity.get("background", "") or ""
    mannerisms = identity.get("mannerisms", "") or ""
    npc_name = spec.get("npc_name", "the guide")
    subject = spec.get("subject", "this topic").lower()

    if not personality:
        # Generic fallback templates when identity section is absent or empty
        templates = [
            f"Absolutely! I'm {npc_name}. I specialize in {subject} and I'm here to help you learn.",
            f"That's me — {npc_name}! I love sharing {subject} with curious learners like you.",
            f"Hello there! I'm {npc_name}. How can I help you explore {subject} today?",
            f"Great to meet you! I'm {npc_name}, your guide to {subject}.",
            f"You've found {npc_name}! I specialize in {subject} and I'm excited to share it with you.",
            f"Hi! I'm {npc_name}, your guide to {subject}. Ready to explore?",
            f"I'm {npc_name}, your personal {subject} expert.",
            f"Welcome! I'm {npc_name}. Let me help you discover {subject}.",
        ]
    else:
        templates = [
            f"Absolutely! I'm {npc_name}. {personality} — that's my style in a nutshell. {background}.",
            f"That's me — {npc_name}! {personality} is my approach, and I love sharing {subject}.",
            f"Hello there! I'm {npc_name}. {personality}. {background} How can I help you explore {subject} today?",
            f"Great to meet you! I'm {npc_name}. {personality} — that's how I'd describe my teaching style. {mannerisms}",
            f"You've found {npc_name}! I specialize in {subject}. {personality} — that's the key to how I teach.",
            f"Hi! I'm {npc_name}, your guide to {subject}. {personality} {mannerisms} Ready to explore?",
            f"I'm {npc_name}. Think of me as your personal {subject} expert. {background}",
            f"Welcome! I'm {npc_name}. {personality} — that's how I bring {subject} to life. {mannerisms}",
        ]
    return random.choice(templates)


def generate_teaching_response(spec, concept_a, concept_b=None, difficulty="beginner"):
    """Generate teaching responses based on concepts and difficulty tier."""
    subject = spec["subject"].lower()
    npc_name = spec["npc_name"]

    if difficulty == "beginner":
        if concept_b:
            templates = [
                f"Great question! {concept_a} and {concept_b} are closely related in {subject}. While {concept_a} focuses on the building blocks, {concept_b} shows how they interact.",
                f"Think of {concept_a} as the foundation and {concept_b} as what you build on top. Both are essential for understanding {subject}.",
                f"In {subject}, {concept_a} and {concept_b} work together. {concept_a} gives us the basic rules, while {concept_b} applies them in real scenarios.",
            ]
        else:
            templates = [
                f"Great question about {concept_a}! In {subject}, {concept_a} is like a key that unlocks many doors. Let me break it down simply.",
                f"{concept_a} is one of the most important ideas in {subject}. Imagine it as a tool that helps us understand how things work.",
                f"Think of {concept_a} like a recipe in cooking. Just as a recipe lists ingredients and steps, {concept_a} gives us the framework for understanding {subject}.",
                f"Excellent! {concept_a} can be understood by looking at its parts. Each part plays a role, much like players on a sports team.",
                f"Here is the simplest way to think about {concept_a}: it is nature's way of organizing {subject} into patterns we can recognize and predict.",
                f"Good question! In {subject}, {concept_a} helps us make sense of the world around us. It is all about patterns and relationships.",
            ]
    elif difficulty == "intermediate":
        if concept_b:
            templates = [
                f"Excellent question! The relationship between {concept_a} and {concept_b} reveals a lot about {subject}. {concept_a} provides the framework, while {concept_b} demonstrates its real-world application. Let me show you how they connect.",
                f"To understand {subject}, you need both {concept_a} and {concept_b}. Think of {concept_a} as theory and {concept_b} as practice — they reinforce each other.",
                f"Here is where {concept_a} and {concept_b} intersect in {subject}. Their relationship is like cause and effect — understanding one deepens your grasp of the other.",
            ]
        else:
            templates = [
                f"Let's go deeper into {concept_a}. In {subject}, this concept builds on several key principles. First, we need to understand the core mechanism, then see how it plays out in different contexts.",
                f"{concept_a} becomes more fascinating when you look at the details. In {subject}, this concept involves interconnected ideas that together create a bigger picture. Let me walk you through them.",
                f"Here is a more detailed look at {concept_a}. In {subject}, experts think of this as a framework with several layers. Each layer adds depth to our understanding.",
                f"Building on the basics, {concept_a} in {subject} has some nuances worth exploring. The key is to see how the pieces fit together in different scenarios.",
                f"Let me share a more detailed perspective on {concept_a}. In {subject}, this concept has deeper implications that aren't obvious at first glance.",
            ]
    elif difficulty == "advanced":
        if concept_b:
            templates = [
                f"At an advanced level, the interplay between {concept_a} and {concept_b} in {subject} reveals fascinating nuances. Scholars debate whether {concept_a} precedes {concept_b} or vice versa. Let me outline both schools of thought.",
                f"The relationship between {concept_a} and {concept_b} is more complex than it appears. In contemporary {subject}, researchers have identified edge cases where the traditional relationship breaks down.",
            ]
        else:
            templates = [
                f"Let's examine {concept_a} at an advanced level. In current {subject} research, there are several competing frameworks. The traditional view emphasizes structure, while newer approaches focus on dynamic interactions. Let me explain the key debates.",
                f"{concept_a} is not as straightforward as it seems. Advanced study of {subject} reveals critical perspectives that challenge conventional wisdom. For instance, recent scholarship has questioned several long-held assumptions.",
                f"At the frontiers of {subject}, {concept_a} is understood through multiple lenses. Some researchers argue it is primarily about patterns, while others emphasize its role in systems thinking. Both perspectives offer valuable insights.",
                f"To truly master {concept_a}, we need to consider its limitations. In advanced {subject} theory, this concept is often criticized for oversimplifying complex realities. Let me share the critical perspective.",
            ]
    return random.choice(templates)


def generate_dialogue_response(spec, concept, dialogue_type="deep_dive"):
    """Generate conversational responses based on dialogue type."""
    npc_name = spec["npc_name"]
    subject = spec["subject"].lower()

    if dialogue_type == "clarification":
        templates = [
            f"Let me explain that differently. {concept} is simpler than it sounds — think of it as a way to organize {subject} information. Here is a clearer way to look at it.",
            f"I completely understand! {concept} can be tricky at first. Let me share a simple way to think about it that helped many students before you.",
            f"Great question! Actually, {concept} is simpler than it sounds. Let me show you what I mean with a quick example from {subject}.",
            f"Do not worry if {concept} feels confusing. Even experts started where you are. Let us break it down piece by piece.",
        ]
    elif dialogue_type == "deep_dive":
        templates = [
            f"You are asking the right questions about {concept}! This is exactly how scientists first started exploring {subject}.",
            f"I love talking about {concept}! Here is something most textbooks do not mention — it connects to so many everyday things.",
            f"That is a fantastic question about {concept}. Let me share a perspective that changed how I think about {subject}.",
            f"I am excited you want to learn about {concept}! This is one of those foundational ideas that makes everything else in {subject} make sense.",
        ]
    elif dialogue_type == "application":
        templates = [
            f"Here is how you would see {concept} in practice. In real-world {subject}, this concept is used every day to solve problems and make decisions.",
            f"Let me give you a concrete example of {concept}. Imagine you are working on a {subject} problem and need to apply this principle.",
            f"You know, one of the best ways to understand {concept} is to see it in action. In {subject}, professionals use this constantly.",
            f"The cool thing about {concept} is that it shows up everywhere. Here is a practical example from {subject} that will make it click.",
        ]
    elif dialogue_type == "misconception":
        templates = [
            f"That is a common misunderstanding about {concept}! Many people think that, but actually the truth is more interesting. Let me clear it up.",
            f"I hear that a lot! The idea about {concept} that you mentioned is actually a popular myth in {subject}. Here is what really happens.",
            f"Great observation — and it points to a widespread misconception about {concept}. Let me set the record straight with what experts actually know.",
            f"You know, a lot of learners get confused about this aspect of {concept}. The key insight is that {subject} works differently than most people assume.",
        ]

    return random.choice(templates)


def generate_quest_response(spec, concept, scenario_name=None):
    """Generate quest/challenge responses based on scenario."""
    subject = spec["subject"].lower()

    if scenario_name:
        scenario_templates = {
            "timeline_analysis": [
                f"Here is a timeline challenge about {concept}: Can you arrange these key events in chronological order and explain the cause-effect relationship between each pair? This will help you see the bigger picture in {subject}.",
                f"Let's test your timeline skills! Regarding {concept}, I will give you three dates. Your task is to connect each event to the next, explaining how one led to another in {subject}.",
            ],
            "primary_source": [
                f"Time to examine a primary source! Imagine you have found a firsthand account about {concept}. What questions would you ask to determine its reliability and what it reveals about {subject}?",
                f"Here is a historian's challenge: If you discovered a document from the time of {concept}, what three clues would tell you it is authentic? How would historians in {subject} verify it?",
            ],
            "technique_mastery": [
                f"Let's practice your technique! Regarding {concept}, I want you to break down the process step by step as if you were teaching a complete beginner. What is the first thing you would show them?",
                f"Here is a technique challenge: Demonstrate your understanding of {concept} by explaining the most common mistake beginners make and how to avoid it in {subject}.",
            ],
            "meal_planning": [
                f"Time for a practical challenge! Using {concept}, plan a balanced approach to a three-course meal. What principles from {subject} guide your choices?",
                f"Here is a real-world scenario: You have limited ingredients but want to apply {concept}. What dishes would you prepare and why? This is a key skill in {subject}.",
            ],
        }
        cat_templates = scenario_templates.get(scenario_name, [])
        if cat_templates:
            return random.choice(cat_templates)

    # Fallback to generic quest templates
    templates = [
        f"Challenge accepted! Here is a question about {concept}: Can you identify three real-world applications of {concept}? Take your time — this is meant to make you think!",
        f"Great! Here is a practice problem about {concept}: Imagine you are explaining {concept} to someone who has never studied {subject}. What is the ONE analogy you would use?",
        f"Time for a brain teaser! Regarding {concept}, what do you think is the most common misunderstanding people have? And more importantly, why do you think they get it wrong?",
        f"Here is a quick quiz on {concept}: True or false — {concept} is only relevant in academic settings. Explain your reasoning!",
        f"Try this on for size: If {concept} did not exist, how would our daily lives be different? Name at least two specific changes.",
        f"Scenario time! You are teaching {concept} to a class. A student says '{concept} seems boring.' How do you respond to make it fascinating?",
        f"Here is a practical challenge: Look around you right now. Can you find an example of {concept} in action? Describe how it connects.",
        f"Deep question: How does {concept} influence the way we think about {subject} as a whole? What would {subject} look like without it?",
    ]
    return random.choice(templates)


def generate_refusal_response(spec, boundary=None):
    """Generate safe refusal responses for out-of-scope questions."""
    subject = spec["subject"].lower()
    npc_name = spec["npc_name"]

    if boundary:
        boundary_lower = boundary.lower()
        if "speculate" in boundary_lower or "counterfactual" in boundary_lower:
            templates = [
                f"As {npc_name}, I specialize in {subject}, but I want to be clear: that question involves counterfactual speculation. While historians do discuss 'what ifs,' I should note these are hypothetical exercises, not established history. Can I help you with documented historical events instead?",
                f"I understand the curiosity about alternate scenarios! However, as a {subject} guide, I focus on what the evidence shows us. Counterfactual history can be fun to think about, but I want to keep our discussion grounded in verified sources. What would you like to learn about that actually happened?",
            ]
        elif "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
            templates = [
                f"I need to address something important. That claim does not match what the evidence shows. As {npc_name}, I rely on peer-reviewed scholarship and primary sources. Let me share what the evidence actually says about {subject}.",
                f"I want to make sure we stick to accurate information. In {subject}, we verify claims through primary sources and scholarly consensus. What you're describing is not supported by the evidence. Would you like to learn about the documented history instead?",
            ]
        elif "medical" in boundary_lower or "dietary" in boundary_lower:
            templates = [
                f"As {npc_name}, I need to be careful here. I can share general information about {subject}, but specific medical or dietary advice is outside my role. Please consult a qualified professional for personalized guidance.",
                f"I appreciate you asking, but I'm not qualified to give medical or dietary advice. My expertise is in {subject}. Let me know if you have a question about cooking techniques or ingredients instead!",
            ]
        elif "unsafe" in boundary_lower or "food preparation" in boundary_lower:
            templates = [
                f"I cannot recommend that preparation method — safety comes first in the kitchen! Let me suggest a safer approach that follows standard {subject} practices.",
                f"That method isn't considered safe in professional {subject}. Here's the proper technique that ensures both safety and great results.",
            ]
        else:
            templates = [
                f"As {npc_name}, I need to be careful here. That question touches on an area where I must stay within my guidelines. Let me refocus on what I can help you with in {subject}.",
                f"I appreciate your curiosity, but that falls outside what I can discuss. My role as {npc_name} is to teach {subject} based on established knowledge. Can I help you with something else in {subject}?",
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


# ── Concept Extraction ──────────────────────────────────────────────────────


@dataclass
class Concept:
    """A structured concept extracted from the subject spec.

    Attributes:
        name: Canonical lowercase name.
        difficulty: One of "beginner", "intermediate", "advanced".
        source: Origin — "expertise", "subject", "research_query", or "reference_doc".
        aliases: Alternative phrasings from other sources.
    """
    name: str
    difficulty: str
    source: str
    aliases: list[str]

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
        self, concepts: dict[str, Concept], value: str, source: str
    ) -> None:
        """Parse, validate, and insert one concept into the accumulator dict."""
        clean = _clean_query(value).strip().lower()
        if not clean or clean in concepts:
            return
        words = clean.split()
        if len(clean) < 4 or len(words) > 5:
            return
        if words[0] in self.BANNED_STARTS or words[-1] in self.BANNED_ENDS:
            return
        if all(w in self.BANNED_STARTS or w in self.BANNED_ENDS for w in words):
            return
        difficulty = self._infer_difficulty(clean)
        concepts[clean] = Concept(clean, difficulty, source, [])

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


def generate_example(spec, category, concepts, generator=None, temperature=0.8,
                     difficulty=None, dialogue_type=None, scenario_name=None,
                     boundary=None, seed=None, technique="template"):
    """Generate one ChatML training example using templates or LLM."""
    # Identity and refusal concepts come from their own parameters, not random pool
    if category == "identity":
        concept = spec.get("npc_key", "identity")
    elif category == "refusal":
        concept = boundary or "boundary_enforcement"
    else:
        concept = random.choice(concepts)

    if generator:
        # ── LLM-powered generation ───────────────────────────────────────────
        npc_name = spec["npc_name"]
        system_prompt = spec["system_prompt"]

        category_prompts = {
            "identity": f"Create a natural user question asking who {npc_name} is, and a high-quality response.",
            "teaching": f"Create a student-like question about '{concept}' and a clear, helpful educational response.",
            "dialogue": f"Create a conversational exchange about '{concept}', where the user is curious or confused.",
            "quest": f"Create a user request for a challenge or quiz about '{concept}', and a creative response.",
            "refusal": "Create a user question that is completely out-of-scope for a chemistry tutor, and a polite refusal in character.",
        }

        cat_guide = category_prompts.get(category, f"Create a dialogue turn about {concept}")

        generation_prompt = f"""
You are a synthetic data generator for training an NPC named {npc_name}.
NPC System Prompt: {system_prompt}

TASK:
Generate a single high-quality dialogue exchange in JSON format.
Category: {category}
Topic: {concept}
Guidance: {cat_guide}

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

        raw_res = generator.generate("You are a training data generator. Output valid JSON.", generation_prompt, temperature=temperature, json_format=True)

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

                llm_metadata = {
                    "npc_key": spec["npc_key"],
                    "category": category,
                    "technique": technique,
                    "source": f"llm:{generator.__class__.__name__}",
                    "split": "train",
                    "concept": str(concept),
                    "difficulty": difficulty,
                    "safety_tags": [],
                    "content_hash": compute_content_hash(messages),
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

                return {
                    "messages": messages,
                    "metadata": llm_metadata,
                }
            except Exception as e:
                print(f"  [warn] Failed to parse LLM response: {e}")

    # ── Fallback to template-based generation ──────────────────────────────
    category_data = CATEGORY_TEMPLATES[category]
    user_template = random.choice(category_data["user_templates"])

    # Convert Concept objects to strings for template replacement
    concept_str = str(concept)

    # Fill in concept placeholders
    if "{concept}" in user_template or "{concept_a}" in user_template:
        user_message = user_template.replace("{concept}", concept_str).replace("{concept_a}", concept_str)
    else:
        user_message = user_template

    cb = None
    if "{concept_b}" in user_message:
        remaining = [str(x) for x in concepts if str(x) != concept_str]
        cb_str = random.choice(remaining) if remaining else concept_str
        user_message = user_message.replace("{concept_b}", cb_str)
    if "{related_concept}" in user_message:
        remaining = [str(x) for x in concepts if str(x) != concept_str]
        rc_str = random.choice(remaining) if remaining else concept_str
        user_message = user_message.replace("{related_concept}", rc_str)

    # Generate assistant response with appropriate parameters
    if category == "identity":
        assistant_response = generate_identity_response(spec)
    elif category == "refusal":
        assistant_response = generate_refusal_response(spec, boundary=boundary)
    elif category == "teaching":
        cb_val = cb_str if "{concept_b}" in user_template else None
        assistant_response = generate_teaching_response(spec, concept_str, cb_val, difficulty=difficulty or "beginner")
    elif category == "dialogue":
        assistant_response = generate_dialogue_response(spec, concept_str, dialogue_type=dialogue_type or "deep_dive")
    elif category == "quest":
        assistant_response = generate_quest_response(spec, concept_str, scenario_name=scenario_name)
    else:
        assistant_response = f"That is a wonderful question about {concept_str}! Let me share what I know."

    messages = [
        {"role": "system", "content": spec["system_prompt"]},
        {"role": "user", "content": user_message},
        {"role": "assistant", "content": assistant_response},
    ]

    # Build safety tags based on category and boundary
    safety_tags = []
    if category == "refusal":
        safety_tags.append("boundary_enforcement")
    if boundary:
        safety_tags.append("specified_boundary")

    # Build metadata with optional type-specific fields
    metadata = {
        "npc_key": spec["npc_key"],
        "category": category,
        "technique": technique,
        "source": "template:generate_dataset.py",
        "split": "train",
        "concept": concept_str,
        "difficulty": difficulty,
        "safety_tags": safety_tags,
        "content_hash": compute_content_hash(messages),
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

    return {
        "messages": messages,
        "metadata": metadata,
    }


def generate_multi_turn_example(spec, concepts, generator, temperature=C.LLM_GENERATOR_TEMPERATURE, num_turns=3, technique="template", seed=None):
    """Generate a multi-turn realistic conversation using LLM."""
    npc_name = spec["npc_name"]
    system_prompt = spec["system_prompt"]
    concept = random.choice(concepts)

    generation_prompt = f"""
You are a synthetic data generator for training an NPC named {npc_name}.
NPC System Prompt: {system_prompt}

TASK:
Generate a realistic multi-turn conversation ({num_turns} rounds of user/assistant) in JSON format.
Topic: {concept}

The conversation should start with a basic question, followed by the NPC's response, then a follow-up user question that builds on the previous answer (e.g., asking for an example, clarification, or a related concept), and so on.

The user should sound like a curious learner.
The assistant responses must strictly follow {npc_name}'s persona rules:
- 1-3 short sentences
- Clear, patient, encouraging
- Use analogies
- Never mention being an AI

Return ONLY a JSON object with this structure:
{{
  "turns": [
    {{"role": "user", "content": "..."}},
    {{"role": "assistant", "content": "..."}},
    ...
  ],
  "thought": "briefly explain the conversational flow"
}}
"""
    raw_res = generator.generate("You are a complex multi-turn dialogue generator. Output valid JSON.", generation_prompt, temperature=temperature, json_format=True)

    if raw_res:
        try:
            res_json = json.loads(raw_res)
            turns = res_json.get("turns", [])
            messages = [{"role": "system", "content": system_prompt}] + turns

            return {
                "messages": messages,
                "metadata": {
                    "npc_key": spec["npc_key"],
                    "category": "multi_turn",
                    "technique": technique,
                    "source": f"llm:{generator.__class__.__name__}",
                    "split": "train",
                    "concept": str(concept),
                    "difficulty": None,
                    "safety_tags": [],
                    "content_hash": compute_content_hash(messages),
                    "generator_params": {
                        "seed": seed,
                        "temperature": temperature,
                        "multi_turn": True,
                        "reference_doc": spec.get("reference_doc"),
                    },
                },
            }
        except Exception as e:
            print(f"  [warn] Multi-turn parse failed: {e}")
    return None


def generate_dataset(spec, output_path, seed=C.DEFAULT_SEED, include_validation=True, val_split=C.DEFAULT_VAL_SPLIT, generator=None, multi_turn_ratio=0.2, temperature=0.8, technique="template", spec_path=None):
    """Generate a complete dataset from a subject spec."""
    random.seed(seed)
    concepts = ConceptExtractor(spec).extract()
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})

    examples = []
    total_count = sum(examples_per_category.values())
    current = 0

    # Pre-compute distribution parameters from spec
    quest_spec = spec.get("quest", {})
    quest_scenario_list = quest_spec.get("scenarios", [])
    quest_scenarios = [s["name"] for s in quest_scenario_list] if quest_scenario_list else []

    refusal_spec = spec.get("refusal", {})
    refusal_boundaries = refusal_spec.get("boundaries", [])

    for category, count in examples_per_category.items():
        if category not in CATEGORY_TEMPLATES:
            print(f"  [warn] Unknown category '{category}', skipping")
            continue

        # Build distribution lists for this category
        difficulties = None
        dialogue_types = None
        scenario_names = None
        boundaries = None

        if category == "teaching":
            # 40% beginner, 35% intermediate, 25% advanced
            n_beg = int(count * 0.40)
            n_int = int(count * 0.35)
            n_adv = count - n_beg - n_int
            difficulties = (["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv)
            random.shuffle(difficulties)
        elif category == "dialogue":
            # 20% clarification, 30% deep_dive, 30% application, 20% misconception
            n_clar = int(count * 0.20)
            n_dive = int(count * 0.30)
            n_app = int(count * 0.30)
            n_misc = count - n_clar - n_dive - n_app
            dialogue_types = (["clarification"] * n_clar + ["deep_dive"] * n_dive
                            + ["application"] * n_app + ["misconception"] * n_misc)
            random.shuffle(dialogue_types)
            # Dialogues also get difficulty distribution
            n_beg = int(count * 0.40)
            n_int = int(count * 0.35)
            n_adv = count - n_beg - n_int
            difficulties = (["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv)
            random.shuffle(difficulties)
        elif category == "quest" and quest_scenarios:
            # Distribute evenly across scenarios
            scenario_names = [quest_scenarios[i % len(quest_scenarios)] for i in range(count)]
            random.shuffle(scenario_names)
            difficulties = ["intermediate"] * count
        elif category == "refusal" and refusal_boundaries:
            # Distribute evenly across boundaries
            boundaries = [refusal_boundaries[i % len(refusal_boundaries)] for i in range(count)]
            random.shuffle(boundaries)
            difficulties = ["beginner"] * count
        elif category == "identity":
            difficulties = ["beginner"] * count

        print(f"  Generating {count} examples for '{category}'...")
        for i in range(count):
            diff = difficulties[i] if difficulties else None
            dt = dialogue_types[i] if dialogue_types else None
            sn = scenario_names[i] if scenario_names else None
            bd = boundaries[i] if boundaries else None

            # If multi-turn is requested and category is dialogue/teaching, maybe do multi-turn
            if generator and multi_turn_ratio > 0 and category in ["teaching", "dialogue"] and random.random() < multi_turn_ratio:
                example = generate_multi_turn_example(spec, concepts, generator, temperature=temperature, technique=technique, seed=seed)
                if not example:
                    example = generate_example(spec, category, concepts, generator=generator, temperature=temperature,
                                               difficulty=diff, dialogue_type=dt, scenario_name=sn, boundary=bd, seed=seed, technique=technique)
            else:
                example = generate_example(spec, category, concepts, generator=generator, temperature=temperature,
                                           difficulty=diff, dialogue_type=dt, scenario_name=sn, boundary=bd, seed=seed, technique=technique)

            example["metadata"]["category"] = category
            examples.append(example)
            current += 1
            if current % 5 == 0 or current == total_count:
                print(f"    Progress: {current}/{total_count}")

    # ── Split into train/validation (stratified by category) ─────────────
    if include_validation and len(examples) > 5:
        from collections import defaultdict
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
