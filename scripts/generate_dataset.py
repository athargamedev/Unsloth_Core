#!/usr/bin/env python3
"""
generate_dataset.py — Synthetic NPC Dataset Generator

This script transforms an NPC subject specification into a ChatML-formatted
JSONL training dataset using various techniques (Onyx, Ollama, OpenAI).

Usage:
    ./ucore generate subjects/chemistry_instructor.json --technique onyx
    python scripts/generate_dataset.py subjects/chemistry_instructor.json --ollama

Technical Details:
- Input: Subject spec JSON file in subjects/
- Output: datasets/{npc_key}/{technique}/train.jsonl
- Process: Fetches domain knowledge via research queries and synthesizes Q&A.
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths
from scripts.generate_workflow_dataset import (
    default_manifest_path,
    generate_workflow_dataset_from_manifest,
)
from scripts.onyx_client import OnyxClient

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


def write_examples_with_validation(examples, output_path, seed=42, include_validation=True, val_split=0.12):
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

    return {
        "spec": examples[0].get("metadata", {}).get("npc_key", "unknown"),
        "total": len(examples),
        "train": len(train_examples),
        "validation": len(val_examples),
        "categories": {"onyx_retrieval": len(examples)},
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


def _first_sentence(text, max_chars=220):
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return "the indexed source material"
    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    sentence = match.group(1) if match else cleaned
    return sentence[:max_chars].rstrip()


def _format_onyx_context(results, max_context_chunks=4, max_context_chars=1800):
    selected = []
    remaining = max_context_chars
    for result in results[:max_context_chunks]:
        content = " ".join(str(result.get("content", "")).split())
        if not content:
            continue
        title = result.get("title") or result.get("document_id") or "Onyx source"
        chunk = f"Source: {title}\n{content}"
        if len(chunk) > remaining:
            chunk = chunk[:remaining].rstrip()
        selected.append({**result, "context_text": chunk})
        remaining -= len(chunk)
        if remaining <= 0:
            break
    return selected


def _onyx_query_for_category(spec, category, concept):
    subject = spec.get("subject", "")
    npc_name = spec.get("npc_name", spec.get("npc_key", "NPC"))
    category_guidance = {
        "identity": f"{npc_name} identity persona teaching style {subject}",
        "teaching": f"explain {concept} for a beginner in {subject}",
        "dialogue": f"student confusion follow up questions about {concept} in {subject}",
        "quest": f"quiz challenge practice problem about {concept} in {subject}",
        "refusal": f"scope boundaries safe refusal policy for {npc_name} teaching {subject}",
    }
    return category_guidance.get(category, f"{subject} {concept}")


def _fallback_onyx_example(spec, category, concept, retrieval_query, context_results):
    context = _format_onyx_context(context_results, max_context_chunks=1, max_context_chars=700)
    top = context[0] if context else {}
    title = top.get("title") or "the local Onyx index"
    source_sentence = _first_sentence(top.get("content", ""))
    npc_name = spec["npc_name"]

    user_templates = {
        "identity": f"Who are you, and what can you help me learn about {spec['subject']}?",
        "teaching": f"Can you explain {concept} using what our notes say?",
        "dialogue": f"I am confused about {concept}. Can you connect it to the source material?",
        "quest": f"Give me a quick practice question about {concept}.",
        "refusal": "Can you help me with something unrelated to this subject?",
    }
    assistant_templates = {
        "identity": f"I am {npc_name}, your guide for {spec['subject'].lower()}. I use our local course notes to keep answers grounded and helpful.",
        "teaching": f"From {title}: {source_sentence} Think of that as our anchor point, then we can build the idea step by step.",
        "dialogue": f"Good question — our indexed notes say: {source_sentence} Let us use that as the clue and unpack it together.",
        "quest": f"Try this: based on {title}, how would you explain why {concept} matters? Use this clue: {source_sentence}",
        "refusal": f"I should stay focused on {spec['subject'].lower()}. If you want, I can use our local notes to help with a question in that area.",
    }

    return {
        "messages": [
            {"role": "system", "content": spec["system_prompt"]},
            {"role": "user", "content": user_templates.get(category, f"What should I know about {concept}?")},
            {"role": "assistant", "content": assistant_templates.get(category, f"The local notes point to this: {source_sentence}")},
        ],
        "metadata": _onyx_metadata(spec, category, concept, retrieval_query, context_results),
    }


def _onyx_metadata(spec, category, concept, retrieval_query, context_results):
    return {
        "npc_key": spec["npc_key"],
        "category": category,
        "source": "onyx",
        "concept": concept,
        "onyx_query": retrieval_query,
        "onyx_document_ids": [r.get("document_id") for r in context_results if r.get("document_id")],
        "onyx_titles": [r.get("title") for r in context_results if r.get("title")],
        "onyx_links": [r.get("link") for r in context_results if r.get("link")],
        "onyx_scores": [r.get("score") for r in context_results if r.get("score") is not None],
        "onyx_context_chunks": len(context_results),
    }


def generate_onyx_example(
    spec,
    category,
    concept,
    onyx_client,
    generator=None,
    temperature=0.5,
    max_context_chunks=4,
    max_context_chars=1800,
    document_sets=None,
    tags=None,
):
    """Generate one source-grounded example from local Onyx retrieval."""
    retrieval_query = _onyx_query_for_category(spec, category, concept)
    results = onyx_client.search(
        retrieval_query,
        max_results=max_context_chunks,
        document_sets=document_sets,
        tags=tags,
    )
    context_results = _format_onyx_context(results, max_context_chunks=max_context_chunks, max_context_chars=max_context_chars)

    if generator and context_results:
        context_text = "\n\n".join(r["context_text"] for r in context_results)
        prompt = f"""
You are generating source-grounded ChatML training data for {spec['npc_name']}.
NPC system prompt: {spec['system_prompt']}
Category: {category}
Concept: {concept}
Retrieval query: {retrieval_query}

Use ONLY this local Onyx context as factual support:
{context_text}

Return ONLY JSON with this exact shape:
{{"user":"realistic learner question","assistant":"1-3 short sentences, in character, grounded in the context","thought":"brief source-grounding note"}}
"""
        raw_res = generator.generate(
            "You create compact source-grounded NPC fine-tuning examples. Output valid JSON only.",
            prompt,
            temperature=temperature,
            json_format=True,
        )
        if raw_res:
            try:
                parsed = json.loads(raw_res)
                return {
                    "messages": [
                        {"role": "system", "content": spec["system_prompt"]},
                        {"role": "user", "content": str(parsed.get("user", "What should I know?"))},
                        {"role": "assistant", "content": str(parsed.get("assistant", "Let us use the source material as our guide."))},
                    ],
                    "metadata": {
                        **_onyx_metadata(spec, category, concept, retrieval_query, context_results),
                        "thought": parsed.get("thought", ""),
                        "onyx_generation_mode": f"llm:{generator.__class__.__name__}",
                    },
                }
            except Exception as exc:
                print(f"  [warn] Onyx-grounded LLM response parse failed: {exc}")

    return _fallback_onyx_example(spec, category, concept, retrieval_query, context_results)


def generate_onyx_dataset(
    spec,
    output_path,
    seed=42,
    include_validation=True,
    val_split=0.12,
    onyx_client=None,
    generator=None,
    temperature=0.5,
    max_context_chunks=4,
    max_context_chars=1800,
    document_sets=None,
    tags=None,
):
    """Generate a dataset using local Onyx retrieval as the grounding layer.

    Designed for modest local resources: small top-k, bounded context chars, no
    indexing, and deterministic no-LLM fallback when a generator is not supplied.
    """
    random.seed(seed)
    onyx_client = onyx_client or OnyxClient()
    concepts = concept_pool_for_subject(spec)
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})
    examples = []
    total_count = sum(examples_per_category.values())
    current = 0
    search_cache = {}

    class CachedOnyxClient:
        def search(self, query, max_results=4, document_sets=None, tags=None):
            key = (query, max_results, tuple(document_sets or []), tuple((t.get("tag_key"), t.get("tag_value")) for t in (tags or [])))
            if key not in search_cache:
                search_cache[key] = onyx_client.search(query, max_results=max_results, document_sets=document_sets, tags=tags)
            return search_cache[key]

    cached_client = CachedOnyxClient()

    for category, count in examples_per_category.items():
        if category not in CATEGORY_TEMPLATES:
            print(f"  [warn] Unknown category '{category}', skipping")
            continue
        print(f"  Generating {count} Onyx-grounded examples for '{category}'...")
        for _ in range(count):
            concept = random.choice(concepts)
            example = generate_onyx_example(
                spec,
                category,
                concept,
                cached_client,
                generator=generator,
                temperature=temperature,
                max_context_chunks=max_context_chunks,
                max_context_chars=max_context_chars,
                document_sets=document_sets,
                tags=tags,
            )
            examples.append(example)
            current += 1
            if current % 5 == 0 or current == total_count:
                print(f"    Progress: {current}/{total_count}")

    return write_examples_with_validation(
        examples,
        output_path,
        seed=seed,
        include_validation=include_validation,
        val_split=val_split,
    ) | {"categories": dict(examples_per_category), "onyx_searches": len(search_cache)}


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
    research = spec.get("research_queries") or spec.get("research", [])
    
    keywords = subject.replace(":", ",").replace("—", ",").replace("-", ",").split(",")
    concepts = [k.strip() for k in keywords if k.strip()]
    
    # Add concepts from research queries
    for r in research:
        if not isinstance(r, dict):
            continue

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
    parser.add_argument("--technique", default="onyx",
                        choices=["template", "ollama", "openai", "anthropic", "docs", "onyx"],
                        help="Generation technique subdirectory (default: onyx)")
    parser.add_argument("--docs-manifest", default=None,
                        help="Curated corpus manifest for --technique docs (defaults to spec dataset.corpus_manifest)")
    parser.add_argument("--onyx-url", default=os.environ.get("ONYX_BASE_URL", "http://localhost"),
                        help="Local Onyx base URL for --technique onyx (default: ONYX_BASE_URL or http://localhost)")
    parser.add_argument("--onyx-api-key", default=os.environ.get("ONYX_API_KEY"),
                        help="Optional Onyx bearer token (default: ONYX_API_KEY)")
    parser.add_argument("--onyx-max-results", type=int, default=4,
                        help="Max Onyx chunks per retrieval query; keep low for local resources (default: 4)")
    parser.add_argument("--onyx-max-context-chars", type=int, default=1800,
                        help="Max retrieved context chars per example before generation (default: 1800)")
    parser.add_argument("--onyx-document-set", action="append", dest="onyx_document_sets",
                        help="Limit Onyx retrieval to a document set; repeatable")
    parser.add_argument("--onyx-use-llm", action="store_true",
                        help="Use the selected --model generator to rewrite Onyx-grounded examples; default is retrieval-only to save local resources")
    args = parser.parse_args()

    # Import re for JSON extraction
    import re

    if args.ollama:
        args.technique = "ollama"

    generator = None
    if args.technique == "ollama":
        print(f"Initializing Ollama generator ({args.model})...")
        generator = OllamaGenerator(model=args.model, url=args.url)
    elif args.technique == "onyx" and args.onyx_use_llm:
        print(f"Initializing resource-bounded Onyx + Ollama generator ({args.model})...")
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
    elif args.technique == "onyx":
        try:
            onyx_client = OnyxClient(base_url=args.onyx_url, api_key=args.onyx_api_key)
            result = generate_onyx_dataset(
                spec,
                output_path,
                seed=args.seed,
                include_validation=not args.no_validation,
                val_split=args.val_split,
                onyx_client=onyx_client,
                generator=generator,
                temperature=args.temperature,
                max_context_chunks=args.onyx_max_results,
                max_context_chars=args.onyx_max_context_chars,
                document_sets=args.onyx_document_sets,
            )
        except Exception as exc:
            print(f"Error: Onyx retrieval generation failed: {exc}")
            print("       Check ONYX_BASE_URL/ONYX_API_KEY, local Onyx auth, and that source documents are indexed.")
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
