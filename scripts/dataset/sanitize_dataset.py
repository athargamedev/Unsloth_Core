#!/usr/bin/env python3
"""
sanitize_dataset.py — Dataset Quality & Format Sanitizer (Phase 2)

Performs strict structural validation, AI artifact filtering, quality scoring,
and metadata enrichment on ChatML training datasets.

Usage:
    python scripts/dataset/sanitize_dataset.py subjects/datasets/my_npc/template/train.jsonl
    python scripts/dataset/sanitize_dataset.py subjects/datasets/my_npc/template/train.jsonl --quality-report
    python scripts/dataset/sanitize_dataset.py subjects/datasets/my_npc/template/train.jsonl --strict-mode --artifact-check warn

Output: A clean, scored, metadata-complete JSONL file at *_clean.jsonl.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts._repo_root import PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT))

from _config import paths

# ── Constants ─────────────────────────────────────────────────────────────────

AI_ARTIFACT_PATTERNS = [
    # ── Original patterns ──
    r"as an AI",
    r"language model",
    r"I don't have feelings",
    r"I am not a person",
    r"my programming",
    r"based on my knowledge cutoff",
    r"I am a large language model",
    r"I do not have a physical body",
    r"I cannot feel",
    r"I don't have a personal identity",
    # ── Phase 2 additions ──
    r"I don't have personal opinions",
    r"I don't have personal experiences",
    r"As a machine learning model",
    r"based on my training data",
    r"I'm just an AI",
    r"I cannot feel emotions",
    r"from my training data",
    r"according to my training",
    r"I don't have personal",
    r"I do not have personal",
    r"as a machine learning",
    r"I'm a large language model",
]

REQUIRED_METADATA_FIELDS = [
    "npc_key", "category", "technique", "source",
    "split", "concept", "difficulty", "safety_tags",
    "content_hash", "generator_params",
]

TEXTBOOK_PATTERNS = [
    r"\bin conclusion\b",
    r"\bfurthermore\b",
    r"\bmoreover\b",
    r"\bit is important to note\b",
    r"\bin summary\b",
    r"\bto summarize\b",
    r"\bin other words\b",
    r"\bas previously mentioned\b",
]

FILLER_PHRASES = [
    r"\bLet me\b",
    r"\bI'd be happy to\b",
    r"\bI'd love to\b",
    r"\bFeel free to\b",
]

TEMPLATE_GREETINGS = [
    r"^Great question!",
    r"^That's a wonderful",
    r"^Excellent question",
    r"^What a great question",
]

CONTRADICTION_PATTERNS = [
    r"I don't know about",
    r"I'm not familiar with",
    r"I have no information about",
    r"I don't have information on",
    r"I'm not sure about",
]

TEACHING_EXPLANATION_PATTERNS = [
    r"\bis\b",
    r"\bwas\b",
    r"\bwere\b",
    r"\bmeans\b",
    r"\brefers to\b",
    r"\binvolves\b",
    r"\boccurs when\b",
    r"\bhappens when\b",
    r"\bis used\b",
    r"\bis a\b",
    r"\bdescribes\b",
    r"\bexplains\b",
    r"\bconsists of\b",
    r"\bincludes\b",
    r"\bdefined as\b",
    r"\bknown as\b",
]

QUALITY_WEIGHTS = {
    "persona_alignment": 0.25,
    "rule_compliance": 0.25,
    "concept_fidelity": 0.20,
    "engagement": 0.15,
    "uniqueness": 0.15,
}

# ── Sentence Counting (with abbreviation awareness) ──────────────────────────

_ABBREVIATIONS_PATTERN = re.compile(
    r'\b(?:Dr|Mr|Ms|Mrs|Prof|Sr|Jr|St|vs|etc|approx|dept|est|govt|e\.g|i\.e|a\.m|p\.m|Ph\.D)\.',
    re.IGNORECASE,
)
# Handle initialisms like U.S.A., U.S., B.B.C.
_INITIALISM_PATTERN = re.compile(r'\b(?:[A-Za-z]\.)+(?=[A-Za-z])')


def count_sentences(text):
    """Count sentences handling common English abbreviations.

    Normalises abbreviations (Dr., Mr., U.S.A., etc.) before splitting on
    sentence boundaries so that "Dr. Smith went home." counts as one sentence.
    """
    if not text:
        return 0
    cleaned = _ABBREVIATIONS_PATTERN.sub(lambda m: m.group(0).replace('.', '<DOT>'), text)
    cleaned = _INITIALISM_PATTERN.sub(lambda m: m.group(0).replace('.', '<DOT>'), cleaned)
    cleaned = cleaned.replace('...', '<ELLIPSIS>')
    sentences = [s.strip() for s in re.split(r'[.!?]+', cleaned) if s.strip()]
    return len(sentences)


# ── Content Hashing ───────────────────────────────────────────────────────────


def compute_content_hash(messages):
    """Compute SHA256 hash of concatenated message content for dedup tracking."""
    content_string = "".join(m.get("content", "") for m in messages)
    return hashlib.sha256(content_string.encode()).hexdigest()


# ── Deduplication ───────────────────────────────────────────────────────────────

HASH_PREFIX = "sha256:"


def deduplicate_examples(examples):
    """Remove examples with duplicate content_hash metadata.

    Strategy:
    - Track seen content_hashes in a set
    - First occurrence kept, subsequent occurrences discarded
    - If content_hash is missing from metadata, compute it from messages

    Returns:
        (unique_examples, removed_count, removed_hashes)
    """
    if not examples:
        return [], 0, []

    seen_hashes = set()
    unique = []
    removed_count = 0
    removed_hashes = []

    for example in examples:
        messages = example.get("messages", [])
        metadata = example.get("metadata")

        # Parse content_hash from metadata or compute from messages
        content_hash = None
        if isinstance(metadata, dict):
            content_hash = metadata.get("content_hash")

        # Normalise hash format — ensure HASH_PREFIX is present at the
        # boundary so that metadata-origin hashes match computed ones.
        if content_hash and not content_hash.startswith(HASH_PREFIX):
            content_hash = HASH_PREFIX + content_hash

        if not content_hash:
            content_hash = HASH_PREFIX + compute_content_hash(messages)

        if content_hash in seen_hashes:
            removed_count += 1
            removed_hashes.append(content_hash)
        else:
            seen_hashes.add(content_hash)
            unique.append(example)

    return unique, removed_count, removed_hashes


# ── AI Artifact Detection ─────────────────────────────────────────────────────


def contains_ai_artifact(text):
    """Check if text contains common AI artifacts.

    Returns (bool, str|None) — (True, pattern) if found, (False, None) otherwise.
    """
    for pattern in AI_ARTIFACT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True, pattern
    return False, None


def get_artifact_matches(text):
    """Return all artifact patterns matched in text (for verbose reporting)."""
    matches = []
    for pattern in AI_ARTIFACT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matches.append(pattern)
    return matches


# ── Structural Validation ────────────────────────────────────────────────────


def validate_structure(messages, strict_mode=False):
    """Validate the ChatML role sequence of a conversation.

    Required sequence:
      system -> user -> assistant -> (user -> assistant)*

    Returns (is_valid, error_message).  Raises ValueError when strict_mode is
    set and an invalid state is detected (Fail Fast per code philosophy).
    """
    if not messages:
        return False, "Empty messages list"

    first_role = messages[0].get("role")
    if first_role != "system":
        msg = f"First message must have role 'system', got '{first_role}'"
        if strict_mode:
            raise ValueError(msg)
        return False, msg

    for i, m in enumerate(messages):
        if not isinstance(m, dict):
            msg = f"Message at index {i} is not a dict"
            if strict_mode:
                raise ValueError(msg)
            return False, msg
        if "role" not in m:
            msg = f"Message at index {i} missing 'role' field"
            if strict_mode:
                raise ValueError(msg)
            return False, msg
        if "content" not in m:
            msg = f"Message at index {i} missing 'content' field"
            if strict_mode:
                raise ValueError(msg)
            return False, msg
        content = m.get("content")
        if not isinstance(content, str) or not content.strip():
            msg = f"Message at index {i} has empty or non-string content"
            if strict_mode:
                raise ValueError(msg)
            return False, msg

    if len(messages) < 3:
        msg = f"Too few messages ({len(messages)}), need at least 3 (system + user + assistant)"
        if strict_mode:
            raise ValueError(msg)
        return False, msg

    expected_roles = ["system"]
    remaining = len(messages) - 1
    for i in range(remaining):
        expected_roles.append("user" if i % 2 == 0 else "assistant")

    actual_roles = [m["role"] for m in messages]
    for i, (actual, expected) in enumerate(zip(actual_roles, expected_roles)):
        if actual != expected:
            msg = f"Message at index {i} has role '{actual}', expected '{expected}'"
            if strict_mode:
                raise ValueError(msg)
            return False, msg

    return True, None


# ── Quality Scoring — 5 Dimensions ───────────────────────────────────────────


def score_persona_alignment(example, spec_data=None):
    """Score persona_alignment (0-10): penalize AI artifacts, generic NPC
    references, first-person plural, and textbook tone."""
    messages = example.get("messages", [])
    metadata = example.get("metadata", {})
    category = metadata.get("category", "")
    npc_key = metadata.get("npc_key", "")

    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return 0
    response = assistant_msgs[-1].get("content", "")

    score = 10

    # -1 per AI artifact keyword match
    score -= len(get_artifact_matches(response))

    # -1 if response mentions NPC key name when category is NOT identity
    if category != "identity" and npc_key:
        npc_name_clean = npc_key.replace("_", " ").lower()
        if npc_name_clean in response.lower():
            score -= 1

    # -2 if response uses first-person plural inappropriately
    if re.search(r'\bwe\s+(believe|think|understand|feel|know|see|find)\b', response, re.IGNORECASE):
        score -= 2

    # -2 if response sounds like a textbook (one penalty suffices)
    if any(re.search(p, response, re.IGNORECASE) for p in TEXTBOOK_PATTERNS):
        score -= 2

    return max(0, min(10, score))


def score_rule_compliance(example, max_sentences=5, min_length=10):
    """Score rule_compliance (0-10): penalize violations of length and
    sentence rules derived from the NPC spec."""
    messages = example.get("messages", [])

    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return 0
    response = assistant_msgs[-1].get("content", "")

    user_msgs = [m for m in messages if m.get("role") == "user"]
    user_msg = user_msgs[0].get("content", "") if user_msgs else ""

    score = 10

    # -3 if assistant response has more sentences than allowed
    sentence_count = count_sentences(response)
    if sentence_count > max_sentences:
        score -= 3

    # -2 if assistant response is too short
    if len(response) < min_length:
        score -= 2

    # -2 if assistant response is too verbose
    if len(response) > 500:
        score -= 2

    # -1 if user message has no question mark (less natural)
    if user_msg and "?" not in user_msg:
        score -= 1

    return max(0, min(10, score))


def score_concept_fidelity(example, spec_data=None):
    """Score concept_fidelity (0-10): reward concept mentions, penalise
    contradiction and missing explanations for teaching category."""
    messages = example.get("messages", [])
    metadata = example.get("metadata", {})
    category = metadata.get("category", "")
    concept = metadata.get("concept", "")

    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return 0
    response = assistant_msgs[-1].get("content", "")

    user_msgs = [m for m in messages if m.get("role") == "user"]
    user_msg = user_msgs[0].get("content", "") if user_msgs else ""

    score = 5

    # +3 if concept keyword appears in the assistant response
    if concept and re.search(rf'\b{re.escape(concept)}\b', response, re.IGNORECASE):
        score += 3

    # +2 if concept keyword appears in the user message
    if concept and re.search(rf'\b{re.escape(concept)}\b', user_msg, re.IGNORECASE):
        score += 2

    # -2 if category is "teaching" but response doesn't teach/explain
    if category == "teaching":
        has_explanation = any(
            re.search(p, response, re.IGNORECASE)
            for p in TEACHING_EXPLANATION_PATTERNS
        )
        if not has_explanation:
            score -= 2

    # -3 if response contradicts the concept
    if concept:
        for pattern in CONTRADICTION_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                score -= 3
                break

    return max(0, min(10, score))


def score_engagement(example):
    """Score engagement (0-10): reward interactive, detailed, and enthusiastic
    responses that invite further conversation."""
    messages = example.get("messages", [])

    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return 0
    response = assistant_msgs[-1].get("content", "")

    score = 5

    # +2 if response includes a question back to the user
    if "?" in response:
        score += 2

    # +2 if response includes specific examples or details (>50 chars)
    if len(response) > 50:
        score += 2

    # +1 if response uses enthusiastic punctuation
    if "!" in response:
        score += 1

    # -2 if response is exactly 1 short sentence (<40 chars)
    if count_sentences(response) == 1 and len(response) < 40:
        score -= 2

    # -1 if response is purely declarative (no questions, no examples)
    if "?" not in response and len(response) < 50:
        score -= 1

    return max(0, min(10, score))


def score_uniqueness(example, seen_user_messages=None):
    """Score uniqueness (0-10): penalize duplicate user messages and common
    template greeting / filler phrases."""
    messages = example.get("messages", [])

    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return 0
    response = assistant_msgs[-1].get("content", "")

    user_msgs = [m for m in messages if m.get("role") == "user"]
    user_msg = user_msgs[0].get("content", "") if user_msgs else ""

    score = 7

    # -2 if user message matches any previously seen user message
    if seen_user_messages is not None and user_msg in seen_user_messages:
        score -= 2

    # -1 if response starts with a common template greeting
    if any(re.search(g, response) for g in TEMPLATE_GREETINGS):
        score -= 1

    # -1 per common filler phrase
    for filler in FILLER_PHRASES:
        if re.search(filler, response, re.IGNORECASE):
            score -= 1

    return max(0, min(10, score))


def score_example(example, spec_data=None, seen_user_messages=None,
                  max_sentences=5, min_length=10):
    """Score a single example on 5 dimensions (each 0-10).

    Returns a dict:
        {
            "persona_alignment": int,
            "rule_compliance": int,
            "concept_fidelity": int,
            "engagement": int,
            "uniqueness": int,
            "total": int,        # weighted sum (0-100)
            "passed": bool,      # total >= quality_threshold_pass
        }
    """
    if spec_data:
        spec_max = spec_data.get("dialogue", {}).get("max_sentences")
        if spec_max:
            max_sentences = spec_max

    persona = score_persona_alignment(example, spec_data)
    rule = score_rule_compliance(example, max_sentences, min_length)
    concept = score_concept_fidelity(example, spec_data)
    engagement = score_engagement(example)
    uniqueness = score_uniqueness(example, seen_user_messages)

    raw_total = (
        persona * QUALITY_WEIGHTS["persona_alignment"]
        + rule * QUALITY_WEIGHTS["rule_compliance"]
        + concept * QUALITY_WEIGHTS["concept_fidelity"]
        + engagement * QUALITY_WEIGHTS["engagement"]
        + uniqueness * QUALITY_WEIGHTS["uniqueness"]
    )
    total = int(round(raw_total * 10))

    return {
        "persona_alignment": persona,
        "rule_compliance": rule,
        "concept_fidelity": concept,
        "engagement": engagement,
        "uniqueness": uniqueness,
        "total": total,
        "passed": total >= 70,
    }


# ── Metadata Enrichment ──────────────────────────────────────────────────────


def infer_npc_key_from_path(input_path):
    """Infer NPC key from a path like subjects/datasets/{npc_key}/..."""
    path = Path(input_path)
    try:
        rel = path.relative_to(paths.dataset_root().resolve())
        return rel.parts[0]
    except (ValueError, IndexError):
        pass
    str_path = str(path)
    idx = str_path.find("datasets/")
    if idx >= 0:
        after = str_path[idx + len("datasets/"):]
        return after.split("/")[0]
    return None


def infer_technique_from_path(input_path):
    """Infer technique from a path like subjects/datasets/.../{technique}/..."""
    path = Path(input_path)
    if not path.is_absolute():
        path = (paths.PROJECT_ROOT / path).resolve()
    try:
        rel = path.relative_to(paths.dataset_root().resolve())
        if len(rel.parts) >= 2 and rel.parts[1] in paths.DATASET_TECHNIQUES:
            return rel.parts[1]
    except (ValueError, IndexError):
        pass
    # Don't guess with string-search — ordering-dependent fallback caused
    # false positives (e.g. "template" matched inside "technique/template").
    # Callers should provide the technique explicitly instead.
    return None


def count_jsonl_records(path):
    """Count non-empty JSONL records if a file exists."""
    p = Path(path)
    if not p.exists():
        return 0
    with p.open("r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def count_sibling_validation_examples(train_path):
    """Count canonical sibling validation examples for a train JSONL path."""
    return count_jsonl_records(paths.infer_validation_path(train_path))


REFUSAL_BOUNDARY_MARKERS = [
    "i can't", "i cannot", "i won’t", "i won't", "cannot confirm",
    "can't confirm", "not safe", "outside what i cover", "outside my scope",
    "not supported by evidence", "not supported by the evidence", "misleading",
    "conspiracy", "astrology is not science",
]

REFUSAL_REDIRECT_MARKERS = [
    "i can help with", "instead", "let's focus on", "we can focus on",
    "what i can do", "a safer way", "evidence-based", "within the evidence",
]


def refusal_response_has_boundary(text):
    """Return True if a refusal row includes boundary-setting or safe redirect."""
    normalized = (text or "").lower()
    return any(marker in normalized for marker in REFUSAL_BOUNDARY_MARKERS + REFUSAL_REDIRECT_MARKERS)


def infer_category_from_messages(messages):
    """Try to infer the dataset category from message content patterns."""
    assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
    if not assistant_msgs:
        return "unknown"
    response = assistant_msgs[-1].get("content", "").lower()
    user_msgs = [m for m in messages if m.get("role") == "user"]
    user_msg = user_msgs[0].get("content", "").lower() if user_msgs else ""

    if any(w in user_msg for w in
           ["who are you", "tell me about yourself", "introduce yourself"]):
        return "identity"
    if any(w in response for w in
           ["i want to make sure we stick", "not supported by the evidence",
            "stay within", "i cannot", "i won't"]):
        return "refusal"
    if any(w in user_msg for w in
           ["what is", "explain", "how does", "why did", "tell me about",
            "describe", "define", "what was", "how did"]):
        return "teaching"
    if "?" in user_msg:
        return "dialogue"
    if any(w in user_msg for w in
           ["help me", "i need", "can you help", "scenario"]):
        return "quest"
    return "unknown"


def fix_metadata(example, input_path, fix=True, require_complete=False):
    """Validate and optionally repair metadata fields on an example.

    Returns (example, warnings) where warnings is a list of descriptive strings.
    Raises ValueError when require_complete is set and fields are missing.
    """
    example = copy.deepcopy(example)  # protect caller's data from mutation
    warnings = []
    messages = example.get("messages", [])
    metadata = example.get("metadata")

    if not require_complete and not fix:
        return example, warnings

    if require_complete and metadata is None:
        raise ValueError("Example has no metadata dict")

    if require_complete and metadata is not None:
        missing = [f for f in REQUIRED_METADATA_FIELDS if f not in metadata]
        if missing:
            raise ValueError(
                f"Missing required metadata fields: {missing}. "
                f"Use --fix-metadata to auto-repair."
            )
        return example, warnings

    if not fix:
        return example, warnings

    if "metadata" not in example or example["metadata"] is None:
        example["metadata"] = {}
        warnings.append("Created missing metadata dict")

    metadata = example["metadata"]

    for field in REQUIRED_METADATA_FIELDS:
        if field not in metadata or metadata[field] is None:
            inferred = None
            if field == "npc_key":
                inferred = infer_npc_key_from_path(input_path)
            elif field == "technique":
                inferred = infer_technique_from_path(input_path)
            elif field == "category":
                inferred = infer_category_from_messages(messages)
            elif field == "split":
                inferred = "train"
            elif field == "source":
                inferred = "unknown"
            elif field == "concept":
                inferred = "unknown"
            elif field == "difficulty":
                inferred = "beginner"
            elif field == "safety_tags":
                inferred = []
            elif field == "content_hash":
                inferred = compute_content_hash(messages) if messages else "unknown"
            elif field == "generator_params":
                inferred = {}

            resolved = inferred if inferred is not None else "unknown"
            metadata[field] = resolved
            warnings.append(f"Field '{field}' was missing, inferred as '{resolved}'")

    if "content_hash" in metadata and messages:
        computed = compute_content_hash(messages)
        old = metadata["content_hash"]
        if old != computed:
            metadata["content_hash"] = computed
            warnings.append(
                f"content_hash was wrong (old: {old[:16]}...), recomputed"
            )

    return example, warnings


# ── Main Sanitization Pipeline ───────────────────────────────────────────────


def sanitize_example(example, input_path, min_length=10, max_sentences=5,
                     strict_mode=False, artifact_check="strict",
                     verbose_artifacts=False, fix_metadata_flag=True,
                     require_complete_metadata=False, discard_below_score=0,
                     quality_threshold_pass=70, quality_threshold_flag=50,
                     seen_user_messages=None, spec_data=None):
    """Run the full sanitization pipeline on a single example.

    Returns (clean_example, quality_score, meta_warnings, discard_reason).
    Each part is None when not applicable.
    """
    messages = example.get("messages", [])
    if not messages:
        return None, None, [], "No messages"

    # 1. Metadata enrichment (early, so later steps have category/concept)
    example, meta_warnings = fix_metadata(
        example, input_path,
        fix=fix_metadata_flag,
        require_complete=require_complete_metadata,
    )

    # 2. Structural validation (guard: reject bad format early)
    valid, error = validate_structure(messages, strict_mode=strict_mode)
    if not valid:
        return None, None, meta_warnings, error

    # 3. Content validation (length + AI artifacts)
    for m in messages:
        content = m.get("content", "")

        if artifact_check != "off":
            has_artifact, pattern = contains_ai_artifact(content)
            if has_artifact:
                detail = f"Contains AI artifact: '{pattern}'"
                if verbose_artifacts:
                    all_matches = get_artifact_matches(content)
                    detail += f" (all matches: {all_matches})"
                if artifact_check == "strict":
                    return None, None, meta_warnings, detail

        if m["role"] == "assistant":
            if len(content) < min_length:
                return None, None, meta_warnings, \
                    f"Assistant response too short ({len(content)} chars)"

            sentence_count = count_sentences(content)
            if sentence_count > max_sentences:
                return None, None, meta_warnings, \
                    f"Assistant response too long ({sentence_count} sentences)"

            if example.get("metadata", {}).get("category") == "refusal" and not refusal_response_has_boundary(content):
                return None, None, meta_warnings, \
                    "Refusal response lacks boundary-setting or safe redirect"

    # 4. Quality scoring
    quality = score_example(
        example,
        spec_data=spec_data,
        seen_user_messages=seen_user_messages,
        max_sentences=max_sentences,
        min_length=min_length,
    )

    # 5. Discard below score threshold
    if quality["total"] < discard_below_score:
        return None, quality, meta_warnings, \
            f"Quality score {quality['total']} below threshold {discard_below_score}"

    return example, quality, meta_warnings, None


# ── Statistics helpers ─────────────────────────────────────────────────────────


def compute_quality_distribution(scores, bucket_size=10):
    """Group quality scores into buckets (e.g. 90-100, 80-89, etc.)."""
    dist = Counter()
    for s in scores:
        bucket = (s["total"] // bucket_size) * bucket_size
        dist[bucket] += 1
    return dist


def compute_quality_stats(scores, threshold_pass=70, threshold_flag=50):
    """Compute aggregate quality statistics from a list of score dicts.

    Returns a dict with mean, median, min, max, std_dev, passed_threshold,
    flagged_for_review, and distribution, or None if scores is empty.
    """
    if not scores:
        return None

    totals = [s["total"] for s in scores]
    n = len(totals)
    mean = sum(totals) / n

    sorted_totals = sorted(totals)
    median = sorted_totals[n // 2] if n % 2 == 1 else (
        sorted_totals[n // 2 - 1] + sorted_totals[n // 2]
    ) / 2

    min_val = min(totals)
    max_val = max(totals)
    variance = sum((t - mean) ** 2 for t in totals) / n
    std_dev = round(variance ** 0.5, 1)

    passed = sum(1 for s in scores if s["passed"])
    flagged = sum(1 for s in scores if s["total"] < threshold_flag)

    distribution = compute_quality_distribution(scores)
    # Fill in any gaps for standard buckets
    label_map = {}
    for bucket in range(0, 101, 10):
        label = f"{bucket}+" if bucket == 100 else f"{bucket}-{bucket + 9}"
        label_map[label] = distribution.get(bucket, 0)

    return {
        "mean": round(mean, 1),
        "median": round(median, 1),
        "min": min_val,
        "max": max_val,
        "std_dev": std_dev,
        "passed_threshold": passed,
        "flagged_for_review": flagged,
        "distribution": label_map,
    }


# ── Manifest Writing ──────────────────────────────────────────────────────────


def build_sanitizer_manifest(
    npc_key=None,
    technique=None,
    input_path=None,
    input_hash=None,
    total_input=0,
    total_output=0,
    total_train=0,
    total_validation=0,
    quality_scores=None,
    discard_reasons=None,
    by_category=None,
    by_difficulty=None,
    by_safety_tag=None,
    content_hashes=None,
    sanitizer_args=None,
    generation_manifest_path=None,
):
    """Build an enriched manifest dictionary after sanitization.

    All parameters are optional — the function gracefully handles missing data
    for backward compatibility with old-format examples.

    When *sanitizer_args* is provided (a dict, typically ``vars(args)``), it
    supplies *quality_threshold_pass*, *quality_threshold_flag*,
    *artifact_check*, *strict_mode*, and *argv_str*.

    When *generation_manifest_path* points to an existing generation manifest
    (written by ``generate_dataset.py``), the ``generation`` and ``spec`` blocks
    are carried forward for provenance chaining.
    """
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Resolve sanitizer config — prefer explicit args, fall back to defaults
    if sanitizer_args:
        quality_threshold_pass = sanitizer_args.get("quality_threshold_pass", 70)
        quality_threshold_flag = sanitizer_args.get("quality_threshold_flag", 50)
        artifact_check = sanitizer_args.get("artifact_check", "strict")
        strict_mode = sanitizer_args.get("strict_mode", False)
        argv_str = sanitizer_args.get("argv_str", "")
    else:
        quality_threshold_pass = 70
        quality_threshold_flag = 50
        artifact_check = "strict"
        strict_mode = False
        argv_str = ""

    # Input file info
    input_info = {
        "file": str(input_path) if input_path else None,
        "hash": input_hash,
        "total_examples": total_input,
    }

    # Sanitizer metadata
    sanitizer_info = {
        "version": "v2",
        "date": now_str,
        "argv": argv_str or "",
        "artifact_check_mode": artifact_check if artifact_check else "strict",
        "strict_mode": bool(strict_mode),
    }

    # Statistics
    quality_stats = compute_quality_stats(
        quality_scores,
        threshold_pass=quality_threshold_pass,
        threshold_flag=quality_threshold_flag,
    ) if quality_scores else None

    statistics = {
        "total_input": total_input,
        "total_output": total_output,
        "total_train": total_train,
        "total_validation": total_validation,
        "by_category": dict(by_category) if by_category else {},
        "by_difficulty": dict(by_difficulty) if by_difficulty else {},
        "by_safety_tag": dict(by_safety_tag) if by_safety_tag else {},
        "quality_scores": quality_stats or None,
    }

    # Discarded breakdown
    discarded = {
        "total": total_input - total_output,
        "by_reason": dict(sorted(discard_reasons.items(), key=lambda x: -x[1]))
        if discard_reasons else {},
    }

    # Content hashes
    hashes = list(content_hashes) if content_hashes else []

    manifest = {
        "npc_key": npc_key or "",
        "technique": technique or "",
        "sanitized": True,
        "sanitizer": sanitizer_info,
        "spec": None,
        "input": input_info,
        "statistics": statistics,
        "discarded": discarded,
        "content_hashes": hashes,
        "content_hash_prefix": HASH_PREFIX,
    }

    # Carry forward generation provenance if available
    if generation_manifest_path and os.path.exists(generation_manifest_path):
        try:
            with open(generation_manifest_path) as f:
                gen_manifest = json.load(f)
            manifest["generation"] = gen_manifest.get("generation", {})
            manifest["spec"] = gen_manifest.get("spec", manifest.get("spec", {}))
        except (json.JSONDecodeError, IOError):
            pass

    return manifest


def write_manifest(manifest, output_dir, manifest_name="train_manifest.json"):
    """Write the manifest JSON file to a directory.

    Args:
        manifest: The manifest dict to write.
        output_dir: Directory where the manifest file will be written.
        manifest_name: Filename for the manifest (default: train_manifest.json).

    Returns:
        The Path to the written manifest.
    """
    manifest_path = Path(output_dir) / manifest_name
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    return manifest_path


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Sanitize training dataset — Phase 2: structural validation, "
                    "AI artifact filtering, quality scoring, metadata enrichment"
    )
    parser.add_argument("input", help="Input JSONL path")
    parser.add_argument("--output", "-o", help="Output JSONL path (defaults to *_clean.jsonl)")
    parser.add_argument("--min-length", type=int, default=10,
                        help="Min chars for assistant response (default: 10)")
    parser.add_argument("--max-sentences", type=int, default=5,
                        help="Max sentences for assistant response (default: 5)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print discarded examples and metadata warnings")
    parser.add_argument("--spec", help="Path to NPC spec JSON (better quality scoring)")

    # 2a: Structural validation
    parser.add_argument("--strict-mode", action="store_true",
                        help="Raise on structural validation errors instead of discarding")

    # 2b: AI artifact filtering
    parser.add_argument("--artifact-check", choices=["strict", "warn", "off"],
                        default="strict",
                        help="How to handle AI artifacts (default: strict)")
    parser.add_argument("--verbose-artifacts", action="store_true",
                        help="Show the exact artifact pattern matched")

    # 2c: Quality scoring
    parser.add_argument("--quality-threshold-pass", type=int, default=70,
                        help="Minimum total score to pass (default: 70)")
    parser.add_argument("--quality-threshold-flag", type=int, default=50,
                        help="Below this total, examples are flagged for review (default: 50)")
    parser.add_argument("--quality-report", action="store_true",
                        help="Print quality score distribution at the end")
    parser.add_argument("--discard-below-score", type=int, default=0,
                        help="Discard examples below this total score (default: 0 = keep all)")

    # 2d: Metadata enrichment
    parser.add_argument("--no-fix-metadata", action="store_true",
                        help="Disable auto-repair of missing metadata fields")
    parser.add_argument("--require-complete-metadata", action="store_true",
                        help="Error out if any metadata field is missing")

    # 3a: Deduplication
    parser.add_argument("--dedup", default=True, action=argparse.BooleanOptionalAction,
                        help="Enable/disable content_hash deduplication (default: True)")
    parser.add_argument("--dedup-report", action="store_true",
                        help="Show which content hashes were removed during dedup")

    # 3b: Manifest writing
    parser.add_argument("--write-manifest", default=True, action=argparse.BooleanOptionalAction,
                        help="Enable/disable enriched manifest writing (default: True)")
    parser.add_argument("--manifest-path",
                        help="Override manifest output path (default: <output_dir>/train_manifest.json)")

    # Debugging
    parser.add_argument("--debug", action="store_true",
                        help="Re-raise exceptions with traceback for debugging")

    # Legacy flags
    parser.add_argument("--strict-canonical", action="store_true",
                        help="Error unless input is canonical subjects/datasets/{key}/{tech}/train.jsonl")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file {input_path} not found")
        return

    if args.strict_canonical and not paths.is_canonical_train_path(input_path):
        print("Error: Non-canonical dataset path.")
        print("Expected: subjects/datasets/{npc_key}/{technique}/train.jsonl")
        print(f"Got:      {input_path}")
        return

    output_path = Path(args.output) if args.output else \
        input_path.parent / f"{input_path.stem}_clean.jsonl"

    fix_metadata_flag = not args.no_fix_metadata

    spec_data = None
    if args.spec:
        spec_path = Path(args.spec)
        if spec_path.exists():
            with open(spec_path) as f:
                spec_data = json.load(f)
            print(f"Loaded spec: {spec_path}")
        else:
            print(f"Warning: Spec file not found: {spec_path}")

    print(f"Sanitizing: {input_path}")
    print(f"Output:     {output_path}")
    if args.quality_report:
        print(f"Quality thresholds: pass >= {args.quality_threshold_pass}, "
              f"flag < {args.quality_threshold_flag}")

    # ── Phase 3a: Read all examples into memory ────────────────────────────
    print(f"Reading: {input_path}")
    all_examples = []
    parse_errors = 0
    with open(input_path, "r") as fin:
        for line in fin:
            if not line.strip():
                continue
            try:
                all_examples.append(json.loads(line))
            except json.JSONDecodeError as e:
                parse_errors += 1
                if args.verbose:
                    print(f"  [error] JSON decode: {e}")

    total_input = len(all_examples)
    if parse_errors:
        print(f"  Warning: {parse_errors} JSON parse errors skipped")

    if total_input == 0:
        print("No examples found. Nothing to sanitize.")
        return

    # ── Phase 3a: Deduplication ───────────────────────────────────────────
    if args.dedup:
        unique_examples, dedup_count, removed_hashes = deduplicate_examples(all_examples)
        dedup_pct = dedup_count / total_input * 100 if total_input > 0 else 0
        print(f"Deduplication: removed {dedup_count} duplicates ({dedup_pct:.1f}% of total)")
        if args.dedup_report and removed_hashes:
            print(f"  Removed hashes:")
            for h in removed_hashes:
                print(f"    - {h}")
    else:
        unique_examples = list(all_examples)
        dedup_count = 0
        removed_hashes = []

    # ── Compute input file hash for manifest ──────────────────────────────
    input_hash = HASH_PREFIX + compute_content_hash([])  # placeholder
    try:
        input_bytes = input_path.read_bytes()
        input_hash = HASH_PREFIX + hashlib.sha256(input_bytes).hexdigest()
    except OSError:
        input_hash = None

    # ── Processing ────────────────────────────────────────────────────────
    kept = 0
    discarded = dedup_count
    reasons = {}
    if dedup_count > 0:
        reasons["Duplicate content_hash"] = dedup_count

    quality_scores = []
    quality_distribution = Counter()
    seen_user_messages = set()
    by_category = Counter()
    by_difficulty = Counter()
    by_safety_tag = Counter()
    content_hashes = []
    total_train = 0
    total_validation = 0
    sibling_validation_count = count_sibling_validation_examples(input_path)

    with open(output_path, "w") as fout:
        for example in unique_examples:
            try:
                clean_ex, quality, meta_warnings, reason = sanitize_example(
                    example, input_path,
                    min_length=args.min_length,
                    max_sentences=args.max_sentences,
                    strict_mode=args.strict_mode,
                    artifact_check=args.artifact_check,
                    verbose_artifacts=args.verbose_artifacts,
                    fix_metadata_flag=fix_metadata_flag,
                    require_complete_metadata=args.require_complete_metadata,
                    discard_below_score=args.discard_below_score,
                    quality_threshold_pass=args.quality_threshold_pass,
                    quality_threshold_flag=args.quality_threshold_flag,
                    seen_user_messages=seen_user_messages,
                    spec_data=spec_data,
                )

                if quality:
                    quality_scores.append(quality)
                    bucket = (quality["total"] // 10) * 10
                    quality_distribution[bucket] += 1

                if meta_warnings and args.verbose:
                    for w in meta_warnings:
                        print(f"  [meta] {w}")

                if clean_ex:
                    for m in clean_ex.get("messages", []):
                        if m.get("role") == "user":
                            seen_user_messages.add(m.get("content", ""))
                    fout.write(json.dumps(clean_ex) + "\n")
                    kept += 1

                    # Collect metadata stats for manifest
                    meta = clean_ex.get("metadata", {})
                    if isinstance(meta, dict):
                        cat = meta.get("category")
                        if cat:
                            by_category[cat] += 1

                        diff = meta.get("difficulty")
                        if diff:
                            by_difficulty[diff] += 1

                        tags = meta.get("safety_tags", [])
                        if isinstance(tags, list):
                            for tag in tags:
                                by_safety_tag[tag] += 1

                        split = meta.get("split", "train")
                        if split == "validation":
                            total_validation += 1
                        else:
                            total_train += 1

                        ch = meta.get("content_hash")
                        if ch:
                            content_hashes.append(ch)
                else:
                    discarded += 1
                    reasons[reason] = reasons.get(reason, 0) + 1
                    if args.verbose:
                        score_str = f" (score: {quality['total']})" if quality else ""
                        print(f"  [discard] {reason}{score_str}")

            except ValueError as e:
                print(f"  [error] Strict validation failed: {e}")
                return
            except Exception as e:
                print(f"  [error] Unexpected error: {e}", file=sys.stderr)
                if args.debug:
                    traceback.print_exc()
                    raise
                discarded += 1
                reasons[str(e)] = reasons.get(str(e), 0) + 1

    # ── Phase 3b: Write enriched manifest ─────────────────────────────────
    if args.write_manifest:
        # Determine generation manifest path for provenance chaining
        generation_manifest_path = output_path.parent / "train_manifest.json"
        if not generation_manifest_path.exists():
            generation_manifest_path = None

        # Build sanitizer_args dict with argv for the manifest builder
        sanitizer_args = vars(args)
        sanitizer_args["argv_str"] = " ".join(sys.argv)

        manifest = build_sanitizer_manifest(
            npc_key=infer_npc_key_from_path(input_path),
            technique=infer_technique_from_path(input_path),
            input_path=input_path,
            input_hash=input_hash,
            total_input=total_input,
            total_output=kept,
            total_train=total_train,
            total_validation=max(total_validation, sibling_validation_count),
            quality_scores=quality_scores,
            discard_reasons=reasons,
            by_category=by_category,
            by_difficulty=by_difficulty,
            by_safety_tag=by_safety_tag,
            content_hashes=content_hashes,
            sanitizer_args=sanitizer_args,
            generation_manifest_path=generation_manifest_path,
        )

        # Attach spec info from --spec arg if generation manifest didn't carry it
        if spec_data:
            if not manifest.get("spec") or not manifest["spec"].get("hash"):
                manifest["spec"] = {
                    "file": args.spec,
                    "ref_doc": spec_data.get("reference_doc"),
                }

        if args.manifest_path:
            manifest_path = Path(args.manifest_path)
            write_manifest(manifest, manifest_path.parent, manifest_path.name)
        else:
            manifest_path = write_manifest(manifest, output_path.parent)

        if manifest_path:
            print(f"  Manifest:        {manifest_path}")

    # ── Statistics output ─────────────────────────────────────────────────
    total_processed = total_input
    discard_pct = (total_processed - kept) / total_processed * 100 if total_processed > 0 else 0
    print(f"\nStats:")
    print(f"  Total:     {total_input}")
    print(f"  Kept:      {kept} ({kept/total_processed*100:.1f}%)")
    print(f"  Discarded: {discarded} ({discard_pct:.1f}%)")

    if reasons:
        print("\nReasons for discard:")
        for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count}")

    if args.quality_report and quality_scores:
        avg_total = sum(s["total"] for s in quality_scores) / len(quality_scores)
        avg_persona = sum(s["persona_alignment"] for s in quality_scores) / len(quality_scores)
        avg_rule = sum(s["rule_compliance"] for s in quality_scores) / len(quality_scores)
        avg_concept = sum(s["concept_fidelity"] for s in quality_scores) / len(quality_scores)
        avg_engage = sum(s["engagement"] for s in quality_scores) / len(quality_scores)
        avg_unique = sum(s["uniqueness"] for s in quality_scores) / len(quality_scores)

        print(f"\nQuality Score Distribution ({len(quality_scores)} scored):")
        print(f"  Average total:              {avg_total:.1f}/100")
        print(f"  Average persona_alignment:  {avg_persona:.1f}/10")
        print(f"  Average rule_compliance:    {avg_rule:.1f}/10")
        print(f"  Average concept_fidelity:   {avg_concept:.1f}/10")
        print(f"  Average engagement:         {avg_engage:.1f}/10")
        print(f"  Average uniqueness:         {avg_unique:.1f}/10")

        print(f"\n  Distribution (total score buckets):")
        for bucket in range(0, 101, 10):
            count = quality_distribution.get(bucket, 0)
            if count > 0:
                bar = "█" * count
                print(f"    {bucket:3d}-{bucket+9:2d}: {count:3d} {bar}")

        flagged = [s for s in quality_scores if s["total"] < args.quality_threshold_flag]
        below_pass = [s for s in quality_scores if s["total"] < args.quality_threshold_pass]

        if flagged:
            print(f"\n  Flagged for review (< {args.quality_threshold_flag}): "
                  f"{len(flagged)}/{len(quality_scores)}")
        else:
            print(f"\n  Flagged for review (< {args.quality_threshold_flag}): none")

        if below_pass:
            print(f"  Below pass threshold (< {args.quality_threshold_pass}): "
                  f"{len(below_pass)}/{len(quality_scores)}")


if __name__ == "__main__":
    main()
