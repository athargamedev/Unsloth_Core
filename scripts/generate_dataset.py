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
from datetime import datetime
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
    """Generate persona self-introduction responses."""
    templates = [
        f"I am {spec['npc_name']}, your guide to {spec['subject'].lower()}.",
        f"Hello! I am {spec['npc_name']}. I can help you learn about {spec['subject'].lower()}.",
        f"Welcome! I am {spec['npc_name']}, here to teach you {spec['subject'].lower()} in a fun way.",
        f"Hi there! I am {spec['npc_name']}. Think of me as your personal tutor for {spec['subject'].lower()}.",
        f"Nice to meet you! I am {spec['npc_name']}. I specialize in explaining {spec['subject'].lower()} clearly.",
        f"I am {spec['npc_name']}, your friendly instructor for all things related to {spec['subject'].lower()}.",
        f"Call me {spec['npc_name']}! I am here to make {spec['subject'].lower()} easy and enjoyable.",
        f"Hello, I am {spec['npc_name']}. Ready to explore {spec['subject'].lower()} together?",
    ]
    return random.choice(templates)


def generate_teaching_response(spec, concept_a, concept_b=None):
    """Generate teaching responses based on concepts."""
    subject = spec["subject"].lower()
    npc_name = spec["npc_name"]

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
    return random.choice(templates)


def generate_dialogue_response(spec, concept):
    """Generate conversational responses."""
    npc_name = spec["npc_name"]
    subject = spec["subject"].lower()
    templates = [
        f"I completely understand! {concept} can be tricky at first. Let me share a simple way to think about it that helped many students before you.",
        f"You are asking the right questions about {concept}! This is exactly how scientists first started exploring {subject}.",
        f"I love talking about {concept}! Here is something most textbooks do not mention — it connects to so many everyday things.",
        f"Do not worry if {concept} feels confusing. Even experts started where you are. Let us break it down piece by piece.",
        f"Fun fact about {concept}: it was discovered by someone who was actually trying to study something else! That is how science works in {subject}.",
        f"You know, understanding {concept} is like learning to ride a bicycle. It seems hard at first, but once it clicks, you will wonder why it ever seemed difficult.",
        f"I am glad you asked about {concept}! Many people find this fascinating once they see how it connects to {subject}.",
        f"Let me tell you a story about {concept}. Stories make ideas stick, and this one is a real game-changer in {subject}.",
        f"Great observation about {concept}! You are thinking like a real {subject} enthusiast.",
        f"Alright, let us tackle {concept} together. Think of me as your thinking partner — we will figure this out step by step.",
        f"I love explaining {concept}! It is one of those topics in {subject} where everything suddenly clicks into place.",
        f"You know what is cool about {concept}? The more you learn, the more you see it everywhere in {subject}.",
        f"That is a fantastic question about {concept}. Let me share a perspective that changed how I think about {subject}.",
        f"Here is a simple way to remember {concept}: think of it as {subject}'s secret superpower. Once you know it, you see it everywhere!",
        f"I am excited you want to learn about {concept}! This is one of those foundational ideas that makes everything else in {subject} make sense.",
        f"Great question! Actually, {concept} is simpler than it sounds. Let me show you what I mean with a quick example from {subject}.",
    ]
    return random.choice(templates)


def generate_quest_response(spec, concept):
    """Generate quest/challenge responses."""
    subject = spec["subject"].lower()
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


def generate_refusal_response(spec):
    """Generate safe refusal responses for out-of-scope questions."""
    subject = spec["subject"].lower()
    npc_name = spec["npc_name"]
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


def concept_pool_for_subject(spec):
    """Extract stable concept keywords from the subject spec.

    Priority order:
      1. teaching.expertise (structured concept list)
      2. Subject description phrase groups
      3. Research query phrases only when they are clean noun-like phrases

    Avoid noisy adjacent-word bigrams like "and causes", "the printing",
    "should know", or "every home" because those pollute metadata, feedback,
    prompts, and portfolio reports.
    """
    concepts = []
    seen = set()

    banned_starts = {
        "a", "an", "and", "are", "as", "basic", "can", "common", "does",
        "every", "for", "from", "how", "in", "key", "major", "of", "should",
        "some", "the", "to", "what", "when", "where", "why", "with",
    }
    banned_ends = {
        "and", "are", "as", "be", "can", "does", "every", "for", "from",
        "how", "in", "of", "should", "some", "the", "to", "what", "when",
        "where", "why", "with",
    }

    def add_concept(value):
        clean = _clean_query(value).strip().lower()
        if not clean or clean in seen:
            return
        words = clean.split()
        if len(clean) < 4 or len(words) > 5:
            return
        if words[0] in banned_starts or words[-1] in banned_ends:
            return
        if all(w in banned_starts or w in banned_ends for w in words):
            return
        concepts.append(clean)
        seen.add(clean)

    # 1. Use structured expertise list (most reliable)
    teaching = spec.get("teaching") or {}
    for exp in teaching.get("expertise") or []:
        add_concept(exp)

    # 2. Parse subject description into meaningful phrase groups
    subject = spec.get("subject", "")
    for sep in [":", "\u2014", "-", ","]:
        subject = subject.replace(sep, "|")
    for phrase in subject.split("|"):
        add_concept(phrase)

    # 3. Keep research queries for retrieval only, not as training concept labels.
    # Query-derived sliding windows caused noisy concepts such as "and causes",
    # "should know", and "the printing". Stable concept labels produce cleaner
    # metadata, feedback reports, and portfolio eval tables.

    if not concepts:
        concepts = ["this topic"]
    return concepts


def generate_example(spec, category, concepts, generator=None, temperature=0.8):
    """Generate one ChatML training example using templates or LLM."""
    if generator:
        # ── LLM-powered generation ───────────────────────────────────────────
        npc_name = spec["npc_name"]
        system_prompt = spec["system_prompt"]
        concept = random.choice(concepts)
        
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
                
                return {
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": assistant_response},
                    ],
                    "metadata": {
                        "npc_key": spec["npc_key"],
                        "category": category,
                        "source": f"ollama:{generator.model}",
                        "concept": concept,
                        "thought": res_json.get("thought", "")
                    },
                }
            except Exception as e:
                print(f"  [warn] Failed to parse LLM response: {e}")

    # ── Fallback to template-based generation ──────────────────────────────
    category_data = CATEGORY_TEMPLATES[category]
    user_template = random.choice(category_data["user_templates"])

    # Fill in concept placeholders
    if "{concept}" in user_template or "{concept_a}" in user_template:
        c = random.choice(concepts)
        user_message = user_template.replace("{concept}", c).replace("{concept_a}", c)
    else:
        c = random.choice(concepts)
        user_message = user_template

    if "{concept_b}" in user_message:
        remaining = [x for x in concepts if x != c]
        cb = random.choice(remaining) if remaining else c
        user_message = user_message.replace("{concept_b}", cb)
    if "{related_concept}" in user_message:
        remaining = [x for x in concepts if x != c]
        rc = random.choice(remaining) if remaining else c
        user_message = user_message.replace("{related_concept}", rc)

    # Generate assistant response
    if category == "identity":
        assistant_response = generate_identity_response(spec)
    elif category == "refusal":
        assistant_response = generate_refusal_response(spec)
    elif category == "teaching":
        cb_val = cb if "{concept_b}" in user_template else None
        assistant_response = generate_teaching_response(spec, c, cb_val)
    elif category == "dialogue":
        assistant_response = generate_dialogue_response(spec, c)
    elif category == "quest":
        assistant_response = generate_quest_response(spec, c)
    else:
        assistant_response = f"That is a wonderful question about {c}! Let me share what I know."

    return {
        "messages": [
            {"role": "system", "content": spec["system_prompt"]},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_response},
        ],
        "metadata": {
            "npc_key": spec["npc_key"],
            "category": category,
            "source": "template",
        },
    }


def generate_multi_turn_example(spec, concepts, generator, temperature=C.LLM_GENERATOR_TEMPERATURE, num_turns=3):
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
                    "source": f"llm:{generator.__class__.__name__}",
                    "concept": concept,
                    "thought": res_json.get("thought", "")
                },
            }
        except Exception as e:
            print(f"  [warn] Multi-turn parse failed: {e}")
    return None


def generate_dataset(spec, output_path, seed=C.DEFAULT_SEED, include_validation=True, val_split=C.DEFAULT_VAL_SPLIT, generator=None, multi_turn_ratio=0.2, temperature=0.8):
    """Generate a complete dataset from a subject spec."""
    random.seed(seed)
    concepts = concept_pool_for_subject(spec)
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})

    examples = []
    total_count = sum(examples_per_category.values())
    current = 0

    for category, count in examples_per_category.items():
        if category not in CATEGORY_TEMPLATES:
            print(f"  [warn] Unknown category '{category}', skipping")
            continue
        print(f"  Generating {count} examples for '{category}'...")
        for _ in range(count):
            # If multi-turn is requested and category is dialogue/teaching, maybe do multi-turn
            if generator and multi_turn_ratio > 0 and category in ["teaching", "dialogue"] and random.random() < multi_turn_ratio:
                example = generate_multi_turn_example(spec, concepts, generator, temperature=temperature)
                if not example:
                    example = generate_example(spec, category, concepts, generator=generator, temperature=temperature)
            else:
                example = generate_example(spec, category, concepts, generator=generator, temperature=temperature)
            
            example["metadata"]["category"] = category
            examples.append(example)
            current += 1
            if current % 5 == 0 or current == total_count:
                print(f"    Progress: {current}/{total_count}")

    # ── Split into train/validation (stratified by category) ─────────────
    if include_validation and len(examples) > 5:
        # Group examples by category for stratified split
        from collections import defaultdict
        by_category = defaultdict(list)
        for ex in examples:
            cat = ex.get("metadata", {}).get("category", "unknown")
            by_category[cat].append(ex)

        train_examples = []
        val_examples = []
        for cat, cat_examples in by_category.items():
            random.shuffle(cat_examples)
            split = max(1, int(len(cat_examples) * val_split))
            val_examples.extend(cat_examples[:split])
            train_examples.extend(cat_examples[split:])

        random.shuffle(train_examples)
        random.shuffle(val_examples)
    else:
        train_examples = examples
        val_examples = []

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

    return {
        "spec": spec["npc_key"],
        "total": len(examples),
        "train": len(train_examples),
        "validation": len(val_examples),
        "categories": dict(examples_per_category),
        "train_path": str(train_path),
        "val_path": str(val_path) if val_path else None,
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
            temperature=args.temperature
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
    print()
    print("Dataset generation complete!")


if __name__ == "__main__":
    main()
