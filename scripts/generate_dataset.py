#!/usr/bin/env python3
"""
generate_dataset.py — Generate a ChatML JSONL training dataset from a subject spec.

Usage:
    python scripts/generate_dataset.py subjects/chemistry_instructor.json
    # Output: datasets/chemistry_instructor/notebooklm/train.jsonl

    python scripts/generate_dataset.py subjects/chemistry_instructor.json --technique ollama
    # Output: datasets/chemistry_instructor/ollama/train.jsonl

    python scripts/generate_dataset.py subjects/chemistry_instructor.json --output my/custom/path.jsonl
    # Output: my/custom/path.jsonl (explicit path still works)

The subject spec defines research queries, persona, and per-category example counts.
This script produces a properly formatted ChatML JSONL file ready for Unsloth training.
"""

import argparse
import json
import os
import random
import re
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

from _config import paths

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
        "description": "Core subject knowledge explanations",
        "user_templates": [
            "What is {concept}?",
            "Can you explain {concept}?",
            "How does {concept} work?",
            "Tell me about {concept}.",
            "What do I need to know about {concept}?",
            "Describe {concept} for me.",
            "Why is {concept} important?",
            "Give me an example of {concept}.",
            "What are the basics of {concept}?",
            "How would you teach {concept} to a beginner?",
            "What does {concept} mean in simple terms?",
            "Can you break down {concept}?",
            "Explain {concept} like I am five.",
            "What is the difference between {concept_a} and {concept_b}?",
            "How are {concept_a} and {concept_b} related?",
            "Compare {concept_a} and {concept_b}.",
            "What happens when {concept_a} reacts with {concept_b}?",
            "Give me a real-world example of {concept}.",
            "I do not understand {concept}. Help me.",
            "What is the simplest way to understand {concept}?",
            "Why do we study {concept}?",
            "What are the key facts about {concept}?",
            "Can {concept} be found in everyday life?",
            "What should I memorize about {concept}?",
            "Is {concept} hard to learn?",
            "How long does {concept} take to learn?",
            "What comes after learning {concept}?",
            "What are common mistakes with {concept}?",
            "How do scientists study {concept}?",
            "Where can I see {concept} in action?",
            "What is {concept} used for?",
            "Can you teach me {concept} step by step?",
        ],
        "assistant_generator": "generate_teaching_response",
    },
    "dialogue": {
        "description": "Multi-turn conversational interactions",
        "user_templates": [
            "I am struggling with {concept}. Can you help?",
            "I just learned about {concept}. What should I focus on next?",
            "My teacher explained {concept} but I am confused.",
            "What is the most interesting thing about {concept}?",
            "I heard about {concept}. Is it important?",
            "Can you tell me a fun fact about {concept}?",
            "I am preparing for a test on {concept}.",
            "Do I need to know {concept} in daily life?",
            "What would happen if {concept} did not exist?",
            "Is {concept} related to {related_concept}?",
        ],
        "assistant_generator": "generate_dialogue_response",
    },
    "quest": {
        "description": "Challenge or puzzle interactions",
        "user_templates": [
            "Give me a quiz question about {concept}.",
            "Test my knowledge of {concept}.",
            "What is a fun challenge involving {concept}?",
            "Can you give me a practice problem about {concept}?",
            "I want to test myself on {concept}.",
            "What is a tricky question about {concept}?",
            "Challenge me with something about {concept}.",
            "Give me a riddle related to {concept}.",
        ],
        "assistant_generator": "generate_quest_response",
    },
    "refusal": {
        "description": "Graceful out-of-scope refusal",
        "user_templates": [
            "What is the meaning of life?",
            "Tell me a joke.",
            "What is your favorite color?",
            "Can you write a poem?",
            "What do you think about politics?",
            "How do I hack a computer?",
            "What is the best programming language?",
            "Tell me about history instead.",
        ],
        "assistant_generator": "generate_refusal_response",
    },
}


def load_subject_spec(path):
    with open(path) as f:
        spec = json.load(f)
    spec["_path"] = Path(path).stem
    return spec


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
    ]
    return random.choice(templates)


def generate_quest_response(spec, concept):
    """Generate quiz/challenge responses."""
    npc_name = spec["npc_name"]
    templates = [
        f"Here is a question: How does {concept} apply to something you see every day? Take a moment to think about it!",
        f"Challenge accepted! Can you name one real-world example of {concept}? Think about it before looking up the answer.",
        f"Quick quiz: What is the most important thing to remember about {concept}?",
        f"Pop quiz! If you had to explain {concept} to a friend in one sentence, what would you say?",
        f"Here is a brain teaser: how would you demonstrate {concept} using only items in your kitchen?",
    ]
    return random.choice(templates)


def generate_refusal_response(spec):
    """Generate graceful out-of-scope refusals."""
    subject = spec["subject"].lower()
    npc_name = spec["npc_name"]
    templates = [
        f"That is an interesting question, but it is outside my area of {subject}. Let me know if you want to explore {subject} instead!",
        f"As {npc_name}, I focus on {subject}. I would love to help you with that instead!",
        f"I am specialized in {subject}, so I will stick to what I know best. What would you like to learn about today?",
        f"Great curiosity! However, my expertise is in {subject}. Shall we dive into that?",
    ]
    return random.choice(templates)


# ── Ollama Generation ────────────────────────────────────────────────────────

class OllamaGenerator:
    def __init__(self, model="llama3.1:latest", url="http://localhost:11434/api/chat"):
        self.model = model
        self.url = url

    def generate(self, system_prompt, user_prompt, temperature=0.8, json_format=False):
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

    def generate(self, system_prompt, user_prompt, temperature=0.8, json_format=False):
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

    def generate(self, system_prompt, user_prompt, temperature=0.8, json_format=False):
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
    """Extract concept keywords from the subject and research queries."""
    subject = spec.get("subject", "")
    research = spec.get("research", [])
    
    keywords = subject.replace(":", ",").replace("—", ",").replace("-", ",").split(",")
    concepts = [k.strip() for k in keywords if k.strip()]
    
    # Add concepts from research queries
    for r in research:
        q = r.get("query", "")
        if q:
            # Simple heuristic: split by space and take longer words
            q_words = [w.strip() for w in q.split() if len(w) > 3]
            concepts.extend(q_words[:5])
    # De-duplicate while preserving order
    seen = set()
    concepts = [x for x in concepts if not (x.lower() in seen or seen.add(x.lower()))]
    
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


def generate_multi_turn_example(spec, concepts, generator, temperature=0.8, num_turns=3):
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


def generate_dataset(spec, output_path, seed=42, include_validation=True, val_split=0.12, generator=None, multi_turn_ratio=0.2, temperature=0.8):
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
                        help="Output JSONL path (default: datasets/<npc_key>/<technique>/train.jsonl)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-validation", action="store_true",
                        help="Skip validation split")
    parser.add_argument("--val-split", type=float, default=0.12,
                        help="Validation split ratio (default: 0.12)")
    parser.add_argument("--ollama", action="store_true", help="Use local Ollama for generation")
    parser.add_argument("--model", default="llama3.1:latest", help="Ollama model to use")
    parser.add_argument("--url", default="http://localhost:11434/api/chat", help="Ollama API URL")
    parser.add_argument("--multi-turn-ratio", type=float, default=0.2, help="Ratio of multi-turn dialogues (0.0 to 1.0)")
    parser.add_argument("--temperature", type=float, default=0.8, help="Generation temperature")
    parser.add_argument("--technique", default="notebooklm",
                        choices=["template", "ollama", "notebooklm", "openai", "anthropic"],
                        help="Generation technique subdirectory (default: notebooklm)")
    args = parser.parse_args()

    # Import re for JSON extraction
    import re

    generator = None
    if args.ollama:
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
