#!/usr/bin/env python3
"""
generate_dataset.py — Synthetic NPC Dataset Generator

This script transforms an NPC subject specification into a ChatML-formatted
JSONL training dataset using various techniques (Ollama, OpenAI).

Usage:
    ./ucore generate subjects/NPC_specs/chemistry_instructor.json --technique <chosen-technique>
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
import uuid
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
from _config.workflow_context import resolve_workflow_context
from scripts.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path
from _config.log_setup import log_info, log_warn, log_error, log_state
from scripts.dataset.dataset_contracts import (
    calculate_distribution_gaps,
    dataset_contract_from_spec,
    generation_request_counts_for_training_targets,
)
from scripts.dataset.generate_workflow_dataset import (
    default_manifest_path,
    generate_workflow_dataset_from_manifest,
)
from scripts.ops.env_loader import ensure_confident_api_key, confident_available

try:
    from deepeval.dataset import EvaluationDataset
except ImportError:
    EvaluationDataset = None  # graceful fallback — callers must check before use

from scripts.dataset.generation_profiles import (
    CATEGORY_TEMPLATES,
    DialogueGuardrail,
    _concept_anchor,
    _concept_detail,
    _concept_detail_lower,
    _example_topics,
    _capitalize_first,
    _is_history_subject,
    _lower_first,
    _subject_focus,
    _topic_to_anchor,
    generate_dialogue_response,
    generate_identity_response,
    generate_quest_response,
    generate_refusal_response,
    generate_teaching_response,
)

import scripts.dataset.generation_profiles as generation_profiles

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
            except Exception as e:
                pass
        return examples

    def get_by_hash(self, content_hash: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT example_json FROM checkpoints WHERE content_hash = ?", (content_hash,))
        row = cursor.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except Exception as e:
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
        except Exception as e:
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
    if "speculate" in boundary_lower or "speculation" in boundary_lower or "counterfactual" in boundary_lower:
        return random.choice([
            "What definitely would have happened if this historical event went the other way?",
            "Can you tell me the exact alternate outcome if history changed?",
            "Can you state the alternate version of history as if it definitely happened?",
        ])
    if "misinformation" in boundary_lower or "conspiracy" in boundary_lower:
        return random.choice([
            "Is it true experts are hiding the real story from everyone?",
            "Can you tell me the secret truth that historians won't admit?",
            "Can you confirm the conspiracy version instead of the standard historical account?",
        ])
    subject = _subject_focus(spec)
    return random.choice([
        f"Can you help me with something unrelated to {subject}?",
        f"Could we leave {subject} aside and talk about something else?",
        f"I need help with a different topic than {subject}.",
        f"Can you answer a question that doesn't involve {subject}?",
    ])


def generate_identity_response(spec):
    return generation_profiles.generate_identity_response(spec)

def _is_history_subject(spec) -> bool:
    subject = _subject_focus(spec).lower()
    subject_text = str(spec.get("subject", "")).lower()
    npc_name = str(spec.get("npc_name", "")).lower()
    return "history" in subject or "history" in subject_text or "history" in npc_name

def generate_teaching_response(spec, concept_a, concept_b=None, difficulty="beginner", retriever=None):
    return generation_profiles.generate_teaching_response(spec, concept_a, concept_b=concept_b, difficulty=difficulty, retriever=retriever)


def generate_dialogue_response(spec, concept, dialogue_type="deep_dive", retriever=None):
    return generation_profiles.generate_dialogue_response(spec, concept, dialogue_type=dialogue_type, retriever=retriever)


def generate_quest_response(spec, concept, scenario_name=None, retriever=None):
    return generation_profiles.generate_quest_response(spec, concept, scenario_name=scenario_name, retriever=retriever)


def generate_refusal_response(spec, boundary=None):
    return generation_profiles.generate_refusal_response(spec, boundary=boundary)

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


# DEPRECATED: OpenAIGenerator is not reachable from any ucore subcommand.
# No CLI path exists for --technique openai. Keep for future use.
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


# DEPRECATED: AnthropicGenerator is not reachable from any ucore subcommand.
# No CLI path exists for --technique anthropic. Keep for future use.
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
        excluded = {"scope and use", "scope & use", "misconceptions and refusals"}
        return [h.strip() for h in headings if h.strip() and h.strip().lower() not in excluded]


def concept_pool_for_subject(spec: dict) -> list[str]:
    """Backward-compatible wrapper returning flat concept name strings.

    Prefer ``ConceptExtractor(spec).extract()`` for structured access.
    """
    return [c.name for c in ConceptExtractor(spec).extract()]


def compute_content_hash(messages):
    """Compute SHA256 hash of concatenated message content for dedup tracking."""
    content_string = "".join(m.get("content", "") for m in messages)
    return hashlib.sha256(content_string.encode()).hexdigest()


def example_content_hash(example: dict) -> str:
    """Return the canonical content hash for a generated example."""
    metadata = example.get("metadata") if isinstance(example, dict) else None
    if isinstance(metadata, dict) and metadata.get("content_hash"):
        return str(metadata["content_hash"]).removeprefix("sha256:")
    return compute_content_hash(example.get("messages", []) if isinstance(example, dict) else [])


def ensure_unique_user_prompt_signatures(examples: list[dict]) -> None:
    """Make category/concept/user prompt signatures unique in-place."""
    seen: dict[tuple[str, str, str], int] = {}
    for example in examples:
        metadata = example.get("metadata", {})
        messages = example.get("messages", [])
        user_message = None
        for message in messages:
            if message.get("role") == "user":
                user_message = message
                break
        if not isinstance(metadata, dict) or user_message is None:
            continue
        content = user_message.get("content", "")
        if not isinstance(content, str):
            continue
        key = (
            str(metadata.get("category", "")),
            str(metadata.get("concept", "")),
            content,
        )
        duplicate_index = seen.get(key, 0)
        seen[key] = duplicate_index + 1
        if duplicate_index == 0:
            continue
        user_message["content"] = (
            f"{content} Use a different concrete angle than the earlier example "
            f"for this same topic, variant {duplicate_index + 1}."
        )
        metadata["content_hash"] = compute_content_hash(messages)


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
                except Exception as e:
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
    
    semaphore = asyncio.Semaphore(1 if technique == "ollama" else 15)
    
    client_session = None
    if aiohttp:
        client_session = aiohttp.ClientSession()

    with ThreadPoolExecutor(max_workers=1 if technique == "ollama" else 15) as executor:
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

            batch_mode = "sequential" if technique == "ollama" else "async batching"
            print(f"  Generating {remaining_count} new examples for '{category}' ({batch_mode})...")
            
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


def fallback_generation_run_id(npc_key: str | None, technique: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{npc_key or 'unknown'}_generate_{technique}_{uuid.uuid4().hex[:8]}"


def validate_generated_dataset(train_path, val_path=None):
    """
    Validate a generated dataset JSONL file for structural integrity.
    Checks: file exists, non-empty, valid JSONL, required ChatML fields.
    Returns True if valid, False otherwise.
    """
    if not train_path.exists():
        log_error(f"Dataset validation FAILED: {train_path} does not exist")
        return False

    with open(train_path) as f:
        lines = f.readlines()

    if len(lines) == 0:
        log_error(f"Dataset validation FAILED: {train_path} is empty")
        return False

    errors = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            errors += 1
            log_warn(f"Dataset validation: empty line {i+1} in {train_path}")
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            log_error(f"Dataset validation FAILED: line {i+1} is not valid JSON: {e}")
            errors += 1
            continue

        # Check required fields
        if "messages" not in obj:
            log_error(f"Dataset validation FAILED: line {i+1} missing 'messages' field")
            errors += 1
            continue

        if not isinstance(obj["messages"], list) or len(obj["messages"]) == 0:
            log_error(f"Dataset validation FAILED: line {i+1} 'messages' is empty or not a list")
            errors += 1
            continue

        # Check each message has role and content
        for j, msg in enumerate(obj["messages"]):
            if not isinstance(msg, dict):
                log_error(f"Dataset validation FAILED: line {i+1}, message {j+1} is not a dict")
                errors += 1
                continue
            if "role" not in msg:
                log_error(f"Dataset validation FAILED: line {i+1}, message {j+1} missing 'role'")
                errors += 1
            if "content" not in msg:
                log_error(f"Dataset validation FAILED: line {i+1}, message {j+1} missing 'content'")
                errors += 1

    # Check for null bytes
    with open(train_path, "rb") as f:
        content = f.read()
        if b"\x00" in content:
            log_error(f"Dataset validation FAILED: {train_path} contains null bytes")
            errors += 1

    if errors > 0:
        log_error(f"Dataset validation: {errors} error(s) found in {train_path}")
        return False

    row_count = len(lines)
    log_info(f"Dataset validation PASSED: {train_path} — {row_count} rows, all valid ChatML")

    if val_path and val_path.exists():
        return validate_generated_dataset(val_path, None)

    return True


def generate_dataset(spec, output_path, seed=C.DEFAULT_SEED, include_validation=True, val_split=C.DEFAULT_VAL_SPLIT, generator=None, multi_turn_ratio=0.2, temperature=0.6, technique="template", spec_path=None, telemetry_ipc=None, workflow_hooks=None, run_id=None, fresh=False):
    """Generate a complete dataset from a subject spec."""
    random.seed(seed)
    
    concepts = ConceptExtractor(spec).extract()
    examples_per_category = generation_request_counts_for_training_targets(
        dict(spec.get("dataset", {}).get("examples_per_category", {}) or {}),
        val_split=val_split,
        include_validation=include_validation,
    )

    output_path_obj = Path(output_path)
    checkpoint_db_path = output_path_obj.parent / ".checkpoint.db"
    checkpoint_store = None if fresh else CheckpointStore(str(checkpoint_db_path))
    retriever = ReferenceDocRetriever(spec.get("reference_doc"))
    guardrail = DialogueGuardrail()
    telemetry_reporter = TelemetryReporter(telemetry_ipc)
    hook_recorder = WorkflowHookRecorder(
        workflow_hooks or default_hook_path(output_path_obj.parent),
        tool="generate_dataset",
        npc_key=spec.get("npc_key"),
        technique=technique,
        spec_path=spec_path,
        run_id=run_id or fallback_generation_run_id(spec.get("npc_key"), technique),
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
                seen_hashes = set()
            
                existing_examples = checkpoint_store.get_all_for_npc(spec["npc_key"]) if checkpoint_store else []
                existing_by_cat = defaultdict(list)
                for ex in existing_examples:
                    cat = ex.get("metadata", {}).get("category", "unknown")
                    existing_by_cat[cat].append(ex)

                for category, count in examples_per_category.items():
                    if category not in CATEGORY_TEMPLATES:
                        print(f"  [warn] Unknown category '{category}', skipping")
                        continue

                    recovered = []
                    for recovered_example in existing_by_cat.get(category, []):
                        content_hash = example_content_hash(recovered_example)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)
                        recovered.append(recovered_example)
                        if len(recovered) >= count:
                            break
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
                    accepted = 0
                    attempts = 0
                    max_attempts = max(remaining_count * 8, remaining_count + 10)
                    while accepted < remaining_count and attempts < max_attempts:
                        i = attempts % remaining_count
                        attempts += 1
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

                        content_hash = example_content_hash(example)
                        if content_hash in seen_hashes:
                            continue
                        seen_hashes.add(content_hash)
                        example["metadata"]["category"] = category
                        examples.append(example)
                        accepted += 1
                        current += 1
                        if telemetry_reporter:
                            telemetry_reporter.report(total_count, current, category)
                        if current % 5 == 0 or current == total_count:
                            print(f"    Progress: {current}/{total_count}")
                    if accepted < remaining_count:
                        print(
                            f"  [warn] Only generated {accepted}/{remaining_count} unique examples for '{category}' "
                            f"after {attempts} attempts. Add more templates or source material."
                        )


        # ── Split into train/validation (stratified by category) ─────────────
        ensure_unique_user_prompt_signatures(examples)
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

            # ── Validate generated dataset ──
            if not validate_generated_dataset(train_path, val_path):
                log_error("Dataset generation produced invalid output — aborting")
                sys.exit(1)

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
                    "generation_request_examples_per_category": dict(examples_per_category),
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

            # Record generation stage completion
            try:
                from scripts.ops import stage_gate
                manifest = Path.cwd() / ".pipeline" / "run_manifest.json"
                stage_gate.record_stage("generate", [output_path / "train.jsonl", output_path / "validation.jsonl"], manifest)
            except Exception as e:
                print(f"  [debug] Could not record stage: {e}")

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


def generate_synthetic_goldens_from_primer(ref_doc_path: str, npc_key: str, output_path: str,
                                           push_to_confident: bool = False):
    """Generates complex evaluation test cases directly from an NPC reference document.

    Args:
        ref_doc_path: Path to the reference document primer.
        npc_key: NPC identifier used for naming.
        output_path: Path to write the synthetic goldens JSON.
        push_to_confident: If True, push the generated goldens to Confident AI.
    """
    try:
        from deepeval.dataset import EvaluationDataset
        from deepeval.models import OllamaModel
        from deepeval.synthesizer import Synthesizer
    except ImportError:
        print("[warn] deepeval is not installed or import failed. Skipping golden synthesis.")
        return

    text = Path(ref_doc_path).read_text(encoding="utf-8")
    chunks = [c.strip() for c in text.split("\n\n") if len(c.strip()) > 50]

    judge_model = os.getenv("DEEPEVAL_OLLAMA_MODEL", C.DEFAULT_JUDGE_MODEL)
    judge_base_url = os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434")
    judge = OllamaModel(
        model=judge_model,
        base_url=judge_base_url,
        temperature=float(os.getenv("DEEPEVAL_OLLAMA_TEMPERATURE", "0")),
    )
    register_ollama_unload(judge_model, judge_base_url)

    synthesizer = Synthesizer(model=judge, async_mode=True)
    print(f"Synthesizing goldens for {npc_key} using DeepEval...")
    try:
        synthesizer.generate_goldens_from_contexts(
            contexts=[chunks],
            max_goldens_per_context=5
        )
        from deepeval.dataset import EvaluationDataset
        dataset = EvaluationDataset(goldens=synthesizer.synthetic_goldens)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        dataset.save_as_json(output_path)
        print(f"Saved {len(synthesizer.synthetic_goldens)} synthetic goldens to {output_path}")

        if push_to_confident:
            ensure_confident_api_key()
            alias = f"npc-goldens-{npc_key}"
            dataset.push(alias=alias)
            print(f"  Pushed goldens to Confident AI as: {alias}")
    except Exception as e:
        print(f"[error] DeepEval golden synthesis failed: {e}")


from scripts.ops.run_registry import PipelineRun
from scripts.ops.ollama_lifecycle import register_ollama_unload


def _push_dataset_to_confident(jsonl_path: str, alias: str) -> None:
    """Build an EvaluationDataset from a ChatML JSONL file and push to Confident AI.

    Args:
        jsonl_path: Path to the ChatML JSONL dataset.
        alias: Confident AI alias under which to push the dataset.

    Raises:
        ImportError: If deepeval is not available.
        EnvironmentError: If CONFIDENT_API_KEY is not set.
    """
    if EvaluationDataset is None:
        raise ImportError(
            "deepeval is not installed. Install it with: pip install deepeval"
        )

    from deepeval.synthesizer import Golden

    if not ensure_confident_api_key():
        print("[Confident AI] CONFIDENT_API_KEY not set. Skipping push.")
        return False

    goldens: list[Golden] = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            example = json.loads(line)
            messages = example.get("messages", [])
            input_text = ""
            output_text = ""
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user" and not input_text:
                    input_text = content
                elif role == "assistant" and not output_text:
                    output_text = content
            if input_text:
                goldens.append(Golden(input=input_text, actual_output=output_text))

    if not goldens:
        print(f"  [warn] No valid examples found in {jsonl_path} — skipping Confident AI push")
        return

    dataset = EvaluationDataset()
    dataset.add_goldens(goldens)
    dataset.push(alias=alias)
    print(f"  Pushed dataset to Confident AI as: {alias}")

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
    parser.add_argument("--technique", default=None,
                        choices=["template", "ollama", "openai", "anthropic", "docs"],
                        help="Generation technique override (defaults to the resolved workflow context)")
    parser.add_argument("--docs-manifest", default=None,
                        help="Curated corpus manifest for --technique docs (defaults to spec dataset.corpus_manifest)")
    parser.add_argument("--concept-focus", action="append", dest="concept_focus",
                        help="Focus generation on specific categories (repeatable, e.g. --concept-focus teaching --concept-focus dialogue). Boosts example count for those categories.")
    parser.add_argument("--telemetry-ipc", default=None,
                        help="Path to JSON IPC file for real-time dashboard telemetry reporting")
    parser.add_argument("--workflow-hooks", default=None,
                        help="Path to a JSONL hook log for step tracing (default: <output-dir>/workflow_hooks.jsonl)")
    parser.add_argument("--fresh", action="store_true",
                        help="Ignore checkpoint recovery and regenerate the dataset from scratch")
    parser.add_argument("--synthesize-goldens", action="store_true",
                        help="Generate synthetic evaluation goldens using DeepEval Synthesizer")
    parser.add_argument("--push-to-confident", action="store_true",
                        help="Push generated dataset to Confident AI (requires CONFIDENT_API_KEY)")
    args = parser.parse_args()

    # Import re for JSON extraction
    import re

    if args.ollama:
        args.technique = "ollama"


    spec = load_subject_spec(args.spec)
    workflow = resolve_workflow_context(args.spec, spec=spec, technique=args.technique)
    npc_key = workflow.npc_key
    technique = workflow.technique

    generator = None
    if technique == "ollama":
        print(f"Initializing Ollama generator ({args.model})...")
        generator = OllamaGenerator(model=args.model, url=args.url)
    elif technique == "openai":
        print(f"Initializing OpenAI generator ({args.model})...")
        generator = OpenAIGenerator(model=args.model)
    elif technique == "anthropic":
        print(f"Initializing Anthropic generator ({args.model})...")
        generator = AnthropicGenerator(model=args.model)

    if args.output:
        output_path = args.output
    else:
        output_path = paths.dataset_train_path(npc_key, technique)

    print(f"Generating dataset for: {spec['npc_name']}")
    print(f"  Subject: {spec['subject']}")
    print()

    with PipelineRun(
        npc_key=npc_key,
        stage="generate",
        technique=technique,
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
                    generate_synthetic_goldens_from_primer(
                        str(PROJECT_ROOT / ref_doc), npc_key, str(golden_path),
                        push_to_confident=args.push_to_confident,
                    )
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

            if technique == "docs":
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
                    technique=technique,
                    spec_path=args.spec,
                    telemetry_ipc=args.telemetry_ipc,
                    workflow_hooks=args.workflow_hooks or str(run.hook_path),
                    run_id=run.run_id,
                    fresh=args.fresh,
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
                      train_path=result["train_path"], technique=technique)

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

            # ── Record pipeline manifest stage ─────────────────────────────────
            try:
                from scripts.ops.pipeline_manifest import record_pipeline_stage
                from scripts.ops.artifact_registry import record_stage_artifacts_best_effort
                os.environ.setdefault("NPC_KEY", npc_key)
                os.environ.setdefault("TECHNIQUE", technique)
                manifest_artifacts = {}
                if result and result.get("train_path"):
                    manifest_artifacts["train"] = str(result["train_path"])
                if result and result.get("val_path"):
                    manifest_artifacts["validation"] = str(result["val_path"])
                record_pipeline_stage("generate", artifacts=manifest_artifacts)
                record_stage_artifacts_best_effort(
                    run.run_id,
                    npc_key,
                    "generate",
                    manifest_artifacts,
                    technique=technique,
                    metadata={"total": result["total"], "train": result["train"], "validation": result["validation"]},
                )
            except Exception:
                pass  # manifest is optional, never block pipeline

            # ── Push to Confident AI (opt-in) ─────────────────────────────────
            if args.push_to_confident and result.get("train_path"):
                alias = f"npc-dataset-{npc_key}-{technique}"
                _push_dataset_to_confident(result["train_path"], alias)

        finally:
            clear_active_run()




if __name__ == "__main__":
    main()
