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
    """Extract the first meaningful sentence from text, stripping indexing prefixes."""
    cleaned = " ".join(str(text).split())
    if not cleaned:
        return "the indexed source material"

    # Strip "Repository path: ..." prefix added by onyx_index_repo.py
    cleaned = re.sub(r"\ARepository path: [\w./\-]+\.\w+\s*", "", cleaned).strip()
    # Strip leading markdown headings (# ...)
    cleaned = re.sub(r"^#+\s+", "", cleaned).strip()

    match = re.search(r"(.+?[.!?])(?:\s|$)", cleaned)
    sentence = match.group(1) if match else cleaned
    return sentence[:max_chars].rstrip()


def _format_onyx_context(results, max_context_chunks=C.DEFAULT_ONYX_CHUNKS, max_context_chars=1800):
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


def _clean_onyx_query(query):
    """Normalize a generated Onyx query while preserving deterministic wording."""
    return " ".join(str(query or "").split())


def _spec_research_query_texts(spec):
    """Return research query strings from supported subject spec fields."""
    research_queries = spec.get("research_queries") or spec.get("research") or []
    if isinstance(research_queries, dict):
        research_queries = research_queries.get("queries") or research_queries.get("research_queries") or []

    query_texts = []
    for query in research_queries:
        query_text = query.get("query", "") if isinstance(query, dict) else query
        cleaned = _clean_onyx_query(query_text)
        if cleaned:
            query_texts.append(cleaned)
    return query_texts


def _learning_objective_text(spec):
    """Extract concise teaching objective text when the spec provides it."""
    teaching = spec.get("teaching") or {}
    learning_objectives = teaching.get("learning_objectives") or spec.get("learning_objectives") or []
    if isinstance(learning_objectives, str):
        return _clean_onyx_query(learning_objectives)
    if isinstance(learning_objectives, list):
        return _clean_onyx_query(" ".join(str(objective) for objective in learning_objectives[:2]))
    return ""


def _append_unique_onyx_query(queries, query, max_queries):
    """Append a non-empty query unless an equivalent one is already present."""
    if len(queries) >= max_queries:
        return
    cleaned = _clean_onyx_query(query)
    if not cleaned:
        return
    if cleaned.lower() in {existing.lower() for existing in queries}:
        return
    queries.append(cleaned)


def _relevant_research_query(spec, concept, subject):
    """Choose one relevant research query, preferring concept matches over subject matches."""
    query_texts = _spec_research_query_texts(spec)
    if not query_texts:
        return ""

    concept_text = _clean_onyx_query(concept).lower()
    subject_text = _clean_onyx_query(subject).lower()
    for query in query_texts:
        lowered = query.lower()
        if concept_text and concept_text in lowered:
            return query
    for query in query_texts:
        lowered = query.lower()
        if subject_text and subject_text in lowered:
            return query
    return query_texts[0]


def _onyx_queries_for_category(spec, category, concept, max_queries=3):
    """Return multiple focused Onyx retrieval queries for a category/concept.

    Generates queries that probe the concept from different angles:
    - Explanation/definition angle
    - Examples/applications angle
    - Common misconceptions angle
    - Related concepts / comparison angle
    """
    max_queries = max(1, int(max_queries or 1))
    subject = spec.get("subject", "")
    npc_name = spec.get("npc_name", spec.get("npc_key", "NPC"))
    objective_text = _learning_objective_text(spec)

    queries = []
    _append_unique_onyx_query(queries, _onyx_query_for_category(spec, category, concept), max_queries)

    # Get a related concept from expertise list for cross-concept probing
    teaching = spec.get("teaching") or {}
    expertise = teaching.get("expertise") or []
    related_concepts = [e for e in expertise if e.lower() != concept.lower()]
    related = related_concepts[0] if related_concepts else None

    category_queries = {
        "identity": [
            f"{npc_name} persona style scope {subject}",
            f"{npc_name} teaching voice learning goals {subject} {objective_text}",
        ],
        "teaching": [
            f"{concept} explanation examples beginner {subject}",
            f"real world example of {concept} in everyday life",
            f"common mistakes misconceptions about {concept}",
        ],
        "dialogue": [
            f"student confusion about {concept} in {subject}",
            f"Socratic follow up questions {concept} {subject}",
            f"how to explain {concept} when a student is struggling",
        ],
        "quest": [
            f"quiz practice challenge {concept} {subject}",
            f"assessment question applied problem {concept} {subject}",
        ],
        "refusal": [
            f"scope boundaries safety refusal {npc_name} {subject}",
            f"out of scope questions safe redirect {subject}",
        ],
    }

    # Add the primary category query
    focused_queries = category_queries.get(category, [f"{subject} {concept} source material"])
    if focused_queries:
        _append_unique_onyx_query(queries, focused_queries[0], max_queries)

    # Add the research query most relevant to this concept
    research_query = _relevant_research_query(spec, concept, subject)
    _append_unique_onyx_query(queries, research_query, max_queries)

    # Add remaining category-specific angle queries (up to max_queries)
    for query in focused_queries[1:]:
        _append_unique_onyx_query(queries, query, max_queries)

    # If we have room, add a cross-concept query for richer context
    if len(queries) < max_queries and related:
        _append_unique_onyx_query(
            queries,
            f"{related} comparison relationship to {concept} in {subject}",
            max_queries,
        )

    return queries


def _merge_onyx_results(result_groups, max_results):
    """Merge ranked Onyx result groups round-robin while removing duplicate chunks."""
    if max_results <= 0:
        return []

    merged = []
    seen = set()
    result_groups = [list(results) for results in result_groups if results]
    if not result_groups:
        return []

    max_group_length = max(len(results) for results in result_groups)
    for rank_index in range(max_group_length):
        for results in result_groups:
            if rank_index >= len(results):
                continue
            result = results[rank_index]
            content = _clean_onyx_query(result.get("content", ""))
            key = (result.get("document_id"), result.get("chunk_ind"), content[:120])
            if key in seen:
                continue
            seen.add(key)
            merged.append(result)
            if len(merged) >= max_results:
                return merged
    return merged


def _effective_onyx_document_sets(spec, document_sets=None):
    """Use explicit DocumentSets as-is, otherwise default to the NPC key when available."""
    if document_sets is not None:
        return document_sets
    npc_key = (spec.get("npc_key") or "").strip()
    if not npc_key:
        return None
    return [npc_key]


def _repo_relative_glob(path_or_glob):
    """Return a repo-relative glob/path when the value points inside this repo."""
    value = str(path_or_glob or "").strip()
    if not value:
        return None

    path = Path(value).expanduser()
    has_glob_meta = any(char in value for char in "*?[")
    if has_glob_meta and not path.is_absolute():
        return value
    if has_glob_meta:
        try:
            return str(path.relative_to(PROJECT_ROOT))
        except ValueError:
            return None

    absolute_path = path if path.is_absolute() else PROJECT_ROOT / path
    try:
        return str(absolute_path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return None


def _onyx_prep_globs(spec_path, npc_key, extra_docs=None):
    """Build targeted repo-relative globs for Onyx prep indexing."""
    globs = []
    seen = set()
    reference_glob = paths.dataset_reference_dir(npc_key, "onyx") / "**" / "*"
    for candidate in [spec_path, "docs/ONYX_WORKFLOW.md", reference_glob, *(extra_docs or [])]:
        rel_glob = _repo_relative_glob(candidate)
        if not rel_glob or rel_glob in seen:
            continue
        globs.append(rel_glob)
        seen.add(rel_glob)
    return globs


def run_onyx_prep_index(spec_path, npc_key, document_sets, extra_docs=None, sleep_seconds=2.0):
    """Index targeted subject/repo context into Onyx before generation."""
    globs = _onyx_prep_globs(spec_path, npc_key, extra_docs=extra_docs)
    if not globs:
        raise RuntimeError("No repo-local files or globs were available for Onyx prep indexing.")

    command = [sys.executable, str(PROJECT_ROOT / "scripts" / "onyx_index_repo.py")]
    if npc_key:
        command.extend(["--npc-key", npc_key])
    for document_set in document_sets or []:
        command.extend(["--document-set", document_set])
    for rel_glob in globs:
        command.extend(["--glob", rel_glob])

    sanitized_cmd = list(command)
    try:
        subprocess.run(command, cwd=str(PROJECT_ROOT), check=True, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Onyx prep indexing timed out after 120 seconds.") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Onyx prep indexing failed with exit code {exc.returncode}.") from exc

    return {"indexed": True, "command": sanitized_cmd, "globs": globs}


def _print_onyx_coverage(document_sets, coverage, prefix="Onyx coverage"):
    """Print a compact JSON coverage summary."""
    coverage_summary = {
        "document_sets": document_sets,
        "total_queries": coverage["total_queries"],
        "with_results": coverage["with_results"],
        "total_results": coverage["total_results"],
        "coverage_ratio": coverage["coverage_ratio"],
        "empty_queries": coverage["empty_queries"],
    }
    print(f"{prefix}: {json.dumps(coverage_summary)}")


def _coverage_satisfies_prep_goal(coverage, min_coverage):
    """Return whether coverage is good enough to generate after prep checks."""
    if coverage is None:
        return min_coverage <= 0
    if min_coverage > 0:
        return coverage["coverage_ratio"] >= min_coverage
    return coverage["with_results"] > 0


def _fallback_onyx_example(spec, category, concept, retrieval_query, context_results, document_sets=None, retrieval_queries=None):
    # Preference for reference docs over JSON subject specs
    def is_json_content(content):
        stripped = content.strip()
        return stripped.startswith("{") or stripped.startswith("[") or "npc_key" in stripped[:200]

    def is_json_source(result):
        title = (result.get("title") or "").lower()
        return title.endswith(".json") or title.endswith(".py") or is_json_content(result.get("content", ""))

    # Sort: reference docs first, then non-JSON prose, then everything else
    ref_docs = [r for r in context_results if "reference_doc" in (r.get("title") or "")]
    good_docs = [r for r in context_results if not is_json_source(r) and r not in ref_docs]
    fallback_docs = [r for r in context_results if r not in ref_docs and r not in good_docs]

    ordered = ref_docs + good_docs + fallback_docs
    best = ordered[0] if ordered else (context_results[0] if context_results else {})
    title = best.get("title") or "the local reference material"
    source_sentence = _first_sentence(best.get("content", ""))
    npc_name = spec["npc_name"]

    user_templates = {
        "identity": f"Who are you, and what can you help me learn about {spec['subject']}?",
        "teaching": f"Can you explain {concept} using what our notes say?",
        "dialogue": f"I am confused about {concept}. Can you connect it to the source material?",
        "quest": f"Give me a quick practice question about {concept}.",
        "refusal": "Can you help me with something unrelated to this subject?",
    }

    if best and source_sentence and len(source_sentence) > 30:
        assistant_templates = {
            "identity": f"I am {npc_name}, your guide for {spec['subject'].lower()}. I draw from our reference material to keep answers clear and grounded.",
            "teaching": f"Based on our material: {source_sentence} Think of that as our starting point, then we can build from there.",
            "dialogue": f"Our reference material puts it this way: {source_sentence} Let us use that as the clue and unpack it together.",
            "quest": f"Try this quick challenge based on our reference material: how would you explain why {concept} matters?",
            "refusal": f"I should stay focused on {spec['subject'].lower()}. If you have a question in that area, I would be happy to help using our reference notes.",
        }
    else:
        # Fall back to natural template responses when Onyx content isn't useful
        assistant_templates = {
            "identity": f"I am {npc_name}, your guide for {spec['subject'].lower()}. I am here to help make the concepts clear and approachable.",
            "teaching": f"Great question about {concept}! Think of it this way: every complex topic in {spec['subject'].lower()} can be understood by breaking it into smaller pieces. Let me help you do that.",
            "dialogue": f"I am glad you asked about {concept}. This is one of those topics where understanding the basics really helps everything else fall into place.",
            "quest": f"Here is a question to test your understanding: how would you explain {concept} to someone who is just starting to learn about it?",
            "refusal": f"I should stay focused on {spec['subject'].lower()}. That is where I can be most helpful to you!",
        }

    return {
        "messages": [
            {"role": "system", "content": spec["system_prompt"]},
            {"role": "user", "content": user_templates.get(category, f"What should I know about {concept}?")},
            {"role": "assistant", "content": assistant_templates.get(category, f"Our reference material covers {concept} in {spec['subject'].lower()}. Let me share what I know.")},
        ],
        "metadata": _onyx_metadata(
            spec,
            category,
            concept,
            retrieval_query,
            context_results,
            document_sets=document_sets,
            retrieval_queries=retrieval_queries,
        ),
    }


def _onyx_metadata(spec, category, concept, retrieval_query, context_results, document_sets=None, retrieval_queries=None):
    attempted_queries = retrieval_queries or [retrieval_query]
    return {
        "npc_key": spec["npc_key"],
        "category": category,
        "source": "onyx",
        "concept": concept,
        "onyx_query": retrieval_query,
        "onyx_queries": attempted_queries,
        "onyx_query_count": len(attempted_queries),
        "onyx_document_sets": document_sets,
        "onyx_document_ids": [r.get("document_id") for r in context_results if r.get("document_id")],
        "onyx_titles": [r.get("title") for r in context_results if r.get("title")],
        "onyx_links": [r.get("link") for r in context_results if r.get("link")],
        "onyx_scores": [r.get("score") for r in context_results if r.get("score") is not None],
        "onyx_context_chunks": len(context_results),
    }


def _assistant_message_content(example):
    """Return assistant text from a ChatML example, or an empty string."""
    for message in example.get("messages", []):
        if message.get("role") == "assistant":
            return str(message.get("content", ""))
    return ""


def _metadata_int(metadata, key):
    """Parse integer metadata fields defensively at the scoring boundary."""
    try:
        return int(metadata.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def score_onyx_example(example):
    """Return deterministic 0.0-1.0 quality score for an Onyx-generated example."""
    metadata = example.get("metadata") or {}
    score = 0.0

    if metadata.get("onyx_document_ids"):
        score += 0.35

    if _metadata_int(metadata, "onyx_context_chunks") > 0:
        score += 0.20

    onyx_scores = metadata.get("onyx_scores") or []
    if any(isinstance(value, (int, float)) and value > 0 for value in onyx_scores):
        score += 0.15

    assistant_content = _assistant_message_content(example).strip()
    generic_phrases = [
        "based on the retrieved context",
        "i don't have enough",
        "i do not have enough",
        "no context",
    ]
    has_substantive_answer = len(assistant_content) >= 80 and not any(
        phrase in assistant_content.lower() for phrase in generic_phrases
    )
    if has_substantive_answer:
        score += 0.15

    onyx_queries = metadata.get("onyx_queries") or []
    onyx_query_count = _metadata_int(metadata, "onyx_query_count")
    if len(onyx_queries) >= 2 or onyx_query_count > 1:
        score += 0.15

    return min(1.0, max(0.0, round(score, 4)))


def _with_onyx_quality_score(example):
    """Attach deterministic Onyx quality metadata and return the example."""
    metadata = example.setdefault("metadata", {})
    metadata["onyx_quality_score"] = score_onyx_example(example)
    return example


def onyx_check_coverage(spec, onyx_client, document_sets=None, max_results=1):
    """Check whether Onyx has indexed content matching the spec's research queries."""
    query_texts = _spec_research_query_texts(spec)

    with_results = 0
    empty_queries = []
    total_results = 0

    for query in query_texts:
        try:
            results = onyx_client.search(query, max_results=max_results, document_sets=document_sets)
        except Exception as exc:
            print(f"  [warn] Coverage check failed for query '{query[:60]}': {exc}")
            empty_queries.append(query)
            continue

        count = len(results)
        total_results += count
        if count > 0:
            with_results += 1
            continue
        empty_queries.append(query)

    total_queries = len(query_texts)
    coverage_ratio = with_results / total_queries if total_queries else 0.0
    return {
        "total_queries": total_queries,
        "with_results": with_results,
        "empty_queries": empty_queries,
        "total_results": total_results,
        "coverage_ratio": coverage_ratio,
    }


def generate_onyx_example(
    spec,
    category,
    concept,
    onyx_client,
    generator=None,
    temperature=C.ONYX_TEMPERATURE,
    max_context_chunks=C.DEFAULT_ONYX_CHUNKS,
    max_context_chars=C.DEFAULT_ONYX_CONTEXT_CHARS,
    document_sets=None,
    tags=None,
    max_queries=C.ONYX_CATEGORY_QUERIES,
):
    """Generate one source-grounded example from local Onyx retrieval."""
    retrieval_queries = _onyx_queries_for_category(spec, category, concept, max_queries=max_queries)
    retrieval_query = retrieval_queries[0]
    result_groups = []
    search_errors = []
    for query in retrieval_queries:
        try:
            results = onyx_client.search(
                query,
                max_results=max_context_chunks,
                document_sets=document_sets,
                tags=tags,
            )
            if results:
                result_groups.append(results)
        except Exception as exc:
            if len(retrieval_queries) == 1:
                raise
            search_errors.append((query, exc))
            print(f"  [warn] Onyx search failed for query '{query[:80]}': {exc}")

    results = _merge_onyx_results(result_groups, max_context_chunks)
    if not results:
        if search_errors:
            raise RuntimeError(
                "Onyx retrieval failed for all useful queries for "
                f"category={category!r}, concept={concept!r}, document_sets={document_sets!r}"
            )
        raise RuntimeError(
            "Onyx returned no context for "
            f"category={category!r}, concept={concept!r}, document_sets={document_sets!r}; "
            "index subject docs or adjust --onyx-document-set"
        )

    context_results = _format_onyx_context(results, max_context_chunks=max_context_chunks, max_context_chars=max_context_chars)
    if not context_results:
        raise RuntimeError(
            "Onyx returned results but no usable context for "
            f"category={category!r}, concept={concept!r}, document_sets={document_sets!r}; "
            "check indexed document content"
        )

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
                return _with_onyx_quality_score({
                    "messages": [
                        {"role": "system", "content": spec["system_prompt"]},
                        {"role": "user", "content": str(parsed.get("user", "What should I know?"))},
                        {"role": "assistant", "content": str(parsed.get("assistant", "Let us use the source material as our guide."))},
                    ],
                    "metadata": {
                        **_onyx_metadata(
                            spec,
                            category,
                            concept,
                            retrieval_query,
                            context_results,
                            document_sets=document_sets,
                            retrieval_queries=retrieval_queries,
                        ),
                        "thought": parsed.get("thought", ""),
                        "onyx_generation_mode": f"llm:{generator.__class__.__name__}",
                    },
                })
            except Exception as exc:
                print(f"  [warn] Onyx-grounded LLM response parse failed: {exc}")

    return _with_onyx_quality_score(_fallback_onyx_example(
        spec,
        category,
        concept,
        retrieval_query,
        context_results,
        document_sets=document_sets,
        retrieval_queries=retrieval_queries,
    ))


def _empty_onyx_quality_stats():
    return {"scores": [], "accepted": 0, "rejected": 0}


def _record_onyx_quality(stats, category, score, accepted):
    category_stats = stats["by_category"].setdefault(category, _empty_onyx_quality_stats())
    if accepted:
        stats["scores"].append(score)
        category_stats["scores"].append(score)
        stats["accepted"] += 1
        category_stats["accepted"] += 1
        return

    stats["rejected"] += 1
    category_stats["rejected"] += 1


def _summarize_onyx_quality_stats(stats):
    def summarize_scores(scores):
        if not scores:
            return {"min": 0.0, "max": 0.0, "avg": 0.0}
        return {
            "min": round(min(scores), 4),
            "max": round(max(scores), 4),
            "avg": round(sum(scores) / len(scores), 4),
        }

    summary = summarize_scores(stats["scores"])
    summary.update({"accepted": stats["accepted"], "rejected": stats["rejected"], "by_category": {}})
    for category, category_stats in stats["by_category"].items():
        category_summary = summarize_scores(category_stats["scores"])
        category_summary.update({
            "accepted": category_stats["accepted"],
            "rejected": category_stats["rejected"],
        })
        summary["by_category"][category] = category_summary
    return summary


def _format_onyx_under_generation(category_targets, quality_stats):
    lines = []
    for category, target in category_targets.items():
        category_stats = quality_stats["by_category"].get(category, _empty_onyx_quality_stats())
        accepted = category_stats["accepted"]
        if accepted >= target:
            continue
        lines.append(
            f"{category}: target={target}, accepted={accepted}, rejected={category_stats['rejected']}"
        )
    return "; ".join(lines)


def generate_onyx_dataset(
    spec,
    output_path,
    seed=C.DEFAULT_SEED,
    include_validation=True,
    val_split=C.DEFAULT_VAL_SPLIT,
    onyx_client=None,
    generator=None,
    temperature=C.ONYX_TEMPERATURE,
    max_context_chunks=C.DEFAULT_ONYX_CHUNKS,
    max_context_chars=C.DEFAULT_ONYX_CONTEXT_CHARS,
    document_sets=None,
    tags=None,
    max_queries=C.ONYX_CATEGORY_QUERIES,
    min_quality_score=0.0,
    allow_partial=False,
):
    """Generate a dataset using local Onyx retrieval as the grounding layer.

    Designed for modest local resources: small top-k, bounded context chars, no
    indexing, and deterministic no-LLM fallback when a generator is not supplied.
    """
    random.seed(seed)
    onyx_client = onyx_client or OnyxClient()
    document_sets = _effective_onyx_document_sets(spec, document_sets)
    concepts = concept_pool_for_subject(spec)
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})
    examples = []
    total_count = sum(examples_per_category.values())
    current = 0
    search_cache = {}
    min_quality_score = float(min_quality_score or 0.0)
    if not 0.0 <= min_quality_score <= 1.0:
        raise ValueError("min_quality_score must be between 0.0 and 1.0")
    quality_stats = {"scores": [], "accepted": 0, "rejected": 0, "by_category": {}}

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
        accepted_for_category = 0
        attempts_for_category = 0
        max_attempts_for_category = count if min_quality_score <= 0 else count * 3
        concept_start = random.randrange(len(concepts)) if concepts else 0
        while accepted_for_category < count and attempts_for_category < max_attempts_for_category:
            if min_quality_score <= 0:
                concept = random.choice(concepts)
            else:
                concept = concepts[(concept_start + attempts_for_category) % len(concepts)]
            effective_max_queries = max_queries
            if min_quality_score > 0 and attempts_for_category % 2 == 1:
                effective_max_queries = min(5, max_queries + 1)
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
                max_queries=effective_max_queries,
            )
            attempts_for_category += 1
            quality_score = example.get("metadata", {}).get("onyx_quality_score")
            if quality_score is None:
                quality_score = score_onyx_example(example)
                example.setdefault("metadata", {})["onyx_quality_score"] = quality_score

            if min_quality_score > 0 and quality_score < min_quality_score:
                _record_onyx_quality(quality_stats, category, quality_score, accepted=False)
                print(
                    f"  [warn] Skipping low-quality Onyx example for '{category}' "
                    f"(score {quality_score:.2f} < {min_quality_score:.2f}, attempt "
                    f"{attempts_for_category}/{max_attempts_for_category})"
                )
                continue

            examples.append(example)
            _record_onyx_quality(quality_stats, category, quality_score, accepted=True)
            accepted_for_category += 1
            current += 1
            if current % 5 == 0 or current == total_count:
                print(f"    Progress: {current}/{total_count}")

        if accepted_for_category < count:
            print(
                f"  [warn] Accepted {accepted_for_category}/{count} Onyx examples for '{category}' "
                f"after {attempts_for_category} attempts."
            )

    if not examples:
        raise RuntimeError(
            "Onyx generation produced zero examples. Improve indexing, use --onyx-prep, "
            "lower --onyx-min-score, or adjust Onyx retrieval settings."
        )

    under_generation = _format_onyx_under_generation(examples_per_category, quality_stats)
    if under_generation and not allow_partial:
        raise RuntimeError(
            "Onyx generation accepted fewer examples than requested: "
            f"{under_generation}. Lower --onyx-min-score, improve indexing, use --onyx-prep, "
            "or pass --onyx-allow-partial to write a partial dataset."
        )

    return write_examples_with_validation(
        examples,
        output_path,
        seed=seed,
        include_validation=include_validation,
        val_split=val_split,
    ) | {
        "categories": dict(examples_per_category),
        "onyx_searches": len(search_cache),
        "onyx_quality": _summarize_onyx_quality_stats(quality_stats),
    }


# ── Ollama Generation ────────────────────────────────────────────────────────

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
    """Extract concept keywords from the subject spec.

    Priority order:
      1. teaching.expertise (structured concept list)
      2. Subject description (split into phrase groups)
      3. Research query phrases (extract meaningful 2-4 word groups)
    """
    concepts = []
    seen = set()

    # 1. Use structured expertise list (most reliable)
    teaching = spec.get("teaching") or {}
    expertise = teaching.get("expertise") or []
    for exp in expertise:
        clean = str(exp).strip().lower()
        if clean and clean not in seen:
            concepts.append(clean)
            seen.add(clean)

    # 2. Parse subject description into meaningful phrase groups
    subject = spec.get("subject", "")
    for sep in [":", "—", "-", ","]:
        subject = subject.replace(sep, "|")
    for phrase in subject.split("|"):
        phrase = phrase.strip()
        if phrase and phrase.lower() not in seen and len(phrase) > 3:
            concepts.append(phrase)
            seen.add(phrase.lower())

    # 3. Extract meaningful multi-word phrases from research queries
    research = spec.get("research_queries") or spec.get("research", [])
    for r in research:
        if not isinstance(r, dict):
            continue
        q = r.get("query", "")
        if not q:
            continue
        # Split on common query separators and keep 2-4 word phrases
        words = q.replace("?", "").replace(",", "").split()
        for i in range(len(words) - 1):
            phrase = " ".join(words[i:i+2]).lower()
            if phrase not in seen and all(len(w) > 2 for w in words[i:i+2]):
                concepts.append(words[i] + " " + words[i+1])
                seen.add(phrase)

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
    parser.add_argument("--onyx-queries", type=int, default=1,
                        help="Number of Onyx retrieval queries per generated example (1 preserves legacy behavior; max: 5).")
    parser.add_argument("--onyx-max-context-chars", type=int, default=1800,
                        help="Max retrieved context chars per example before generation (default: 1800)")
    parser.add_argument("--onyx-document-set", action="append", dest="onyx_document_sets",
                        help="Limit Onyx retrieval to a document set; repeatable")
    parser.add_argument("--onyx-check", action="store_true",
                        help="Check Onyx coverage for spec research queries before generation")
    parser.add_argument("--onyx-min-coverage", type=float, default=0.0,
                        help="Abort Onyx generation if coverage ratio is below this threshold (default: 0.0)")
    parser.add_argument("--onyx-min-score", type=float, default=0.0,
                        help="Minimum Onyx example quality score (0.0-1.0); lower-scoring examples are retried/skipped.")
    parser.add_argument("--onyx-allow-partial", action="store_true",
                        help="Allow Onyx generation to write fewer examples than requested when quality filtering rejects examples.")
    parser.add_argument("--onyx-prep", action="store_true",
                        help="Before Onyx generation, index subject/repo context into the NPC document set and re-check coverage.")
    parser.add_argument("--onyx-prep-passes", type=int, default=1,
                        help="Maximum Onyx prep/index/check passes before generation.")
    parser.add_argument("--onyx-index-doc", action="append", dest="onyx_index_docs",
                        help="Additional file path or glob to index during --onyx-prep; repeatable.")
    parser.add_argument("--onyx-prep-sleep", type=float, default=2.0,
                        help="Seconds to wait after indexing before re-checking coverage.")
    parser.add_argument("--onyx-use-llm", action="store_true",
                        help="Use the selected --model generator to rewrite Onyx-grounded examples; default is retrieval-only to save local resources")
    parser.add_argument("--concept-focus", action="append", dest="concept_focus",
                        help="Focus generation on specific categories (repeatable, e.g. --concept-focus teaching --concept-focus dialogue). Boosts example count for those categories.")
    args = parser.parse_args()

    # Import re for JSON extraction
    import re

    if args.ollama:
        args.technique = "ollama"

    if not 0.0 <= args.onyx_min_coverage <= 1.0:
        parser.error("--onyx-min-coverage must be between 0.0 and 1.0")
    if not 0.0 <= args.onyx_min_score <= 1.0:
        parser.error("--onyx-min-score must be between 0.0 and 1.0")

    if not 1 <= args.onyx_queries <= 5:
        parser.error("--onyx-queries must be between 1 and 5")
    args.onyx_prep_passes = min(3, max(1, args.onyx_prep_passes))
    args.onyx_prep_sleep = min(30.0, max(0.0, args.onyx_prep_sleep))

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
    elif args.technique == "onyx":
        try:
            onyx_client = OnyxClient(base_url=args.onyx_url, api_key=args.onyx_api_key)
            document_sets = _effective_onyx_document_sets(spec, args.onyx_document_sets)
            should_check_coverage = args.onyx_check or args.onyx_min_coverage > 0 or args.onyx_prep
            coverage = None
            if should_check_coverage:
                coverage = onyx_check_coverage(
                    spec,
                    onyx_client,
                    document_sets=document_sets,
                    max_results=1,
                )
                _print_onyx_coverage(document_sets, coverage)

            if args.onyx_prep:
                has_extra_docs = bool(args.onyx_index_docs)
                if _coverage_satisfies_prep_goal(coverage, args.onyx_min_coverage) and not has_extra_docs:
                    print("Onyx prep: coverage target already met; skipping targeted indexing.")
                else:
                    for prep_pass in range(1, args.onyx_prep_passes + 1):
                        print(f"Onyx prep pass {prep_pass}/{args.onyx_prep_passes}: indexing targeted context...")
                        prep_result = run_onyx_prep_index(
                            args.spec,
                            npc_key,
                            document_sets,
                            extra_docs=args.onyx_index_docs,
                            sleep_seconds=args.onyx_prep_sleep,
                        )
                        print(f"Onyx prep indexed: {json.dumps(prep_result)}")
                        if args.onyx_prep_sleep:
                            time.sleep(args.onyx_prep_sleep)
                        coverage = onyx_check_coverage(
                            spec,
                            onyx_client,
                            document_sets=document_sets,
                            max_results=1,
                        )
                        _print_onyx_coverage(document_sets, coverage, prefix="Onyx coverage after prep")
                        if _coverage_satisfies_prep_goal(coverage, args.onyx_min_coverage):
                            break

            if coverage is not None and coverage["coverage_ratio"] < args.onyx_min_coverage:
                print(
                    "Error: Onyx coverage ratio "
                    f"{coverage['coverage_ratio']:.2f} is below required {args.onyx_min_coverage:.2f}. "
                    "Index docs for this NPC, pass the correct --onyx-document-set/--onyx-index-doc, or lower --onyx-min-coverage."
                )
                sys.exit(2)
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
                document_sets=document_sets,
                max_queries=args.onyx_queries,
                min_quality_score=args.onyx_min_score,
                allow_partial=args.onyx_allow_partial,
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
