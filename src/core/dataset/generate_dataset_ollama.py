#!/usr/bin/env python3
"""
generate_dataset_ollama.py — Ollama-Optimized NPC Dataset Generator

Specialized dataset generation using local Ollama models with:
- Advanced retry logic and fallback handling
- Real-time progress tracking
- Context-aware concept grounding
- Batch generation with concurrency control
- Automatic model detection and fallback

Usage:
    ./ucore generate-ollama subjects/NPC_specs/chemistry_instructor.json --model llama2
    ./ucore generate-ollama subjects/NPC_specs/history_guide.json --batch-size 4 --max-retries 3

Technical Details:
- Ollama API: http://localhost:11434/api/chat
- Default model: llama2 (fast, ~4GB), optionally llama3.1, mistral, neural-chat
- Input: Subject spec JSON file in subjects/NPC_specs/
- Output: subjects/datasets/{npc_key}/ollama/train.jsonl
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
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

try:
    import aiohttp
except ImportError:
    aiohttp = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from src.config import paths, constants as C
from src.config.log_setup import log_info, log_warn, log_error, log_state
from src.config.workflow_context import resolve_workflow_context
from src.core.dataset.dataset_contracts import (
    calculate_distribution_gaps,
    dataset_contract_from_spec,
    generation_request_counts_for_training_targets,
)
from src.core.ops.ollama_lifecycle import register_ollama_unload
from src.core.ops.ollama_model_presets import resolve_ollama_model
from src.core.ops.workflow_hooks import WorkflowHookRecorder, default_hook_path
from src.core.dataset.ollama_artifacts import build_ollama_manifest, write_ollama_dataset_artifacts
from src.core.dataset.generation_profiles import (
    CATEGORY_TEMPLATES,
    DialogueGuardrail,
    _is_history_subject,
    generate_dialogue_response,
    generate_identity_response,
    generate_quest_response,
    generate_refusal_response,
    generate_teaching_response,
)
from generate_dataset import (
    ConceptExtractor,
    ReferenceDocRetriever,
    generate_example_async,
    fallback_generation_run_id,
    _refusal_user_message,
    compute_content_hash,
    load_subject_spec,
)

# ── Setup logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def _ollama_host_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.hostname:
        return "127.0.0.1:11434"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.hostname}:{port}"


def _run_ollama_cli(args, url: str):
    env = os.environ.copy()
    env["OLLAMA_HOST"] = _ollama_host_from_url(url)
    result = subprocess.run(
        ["ollama"] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result


def parse_ollama_ps(output: str) -> list[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    if lines[0].lower().startswith("name"):
        lines = lines[1:]
    models = []
    for line in lines:
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def list_running_ollama_models(url: str) -> list[str]:
    result = _run_ollama_cli(["ps"], url)
    if result.returncode != 0:
        logger.warning(f"Unable to query Ollama running models: {result.stderr.strip()}")
        return []
    return parse_ollama_ps(result.stdout)


def stop_ollama_model(model_name: str, url: str) -> bool:
    result = _run_ollama_cli(["stop", model_name], url)
    if result.returncode != 0:
        logger.warning(f"Failed to stop Ollama model '{model_name}': {result.stderr.strip()}")
        return False
    logger.info(f"Stopped Ollama model: {model_name}")
    return True


def ensure_selected_ollama_model_loaded(model_name: str, url: str, dry_run: bool = False) -> bool:
    running_models = list_running_ollama_models(url)
    if not running_models:
        logger.info("No Ollama model currently loaded.")
        return True

    if model_name in running_models:
        logger.info(f"Selected Ollama model '{model_name}' is already loaded.")
        for other in [m for m in running_models if m != model_name]:
            if dry_run:
                logger.info(f"[DRY-RUN] Would stop loaded Ollama model: {other}")
            else:
                stop_ollama_model(other, url)
        return True

    logger.info(f"Detected other Ollama model(s) loaded: {', '.join(running_models)}")
    if dry_run:
        logger.info(f"[DRY-RUN] Would stop all loaded models and load '{model_name}'")
        return True

    for other in running_models:
        stop_ollama_model(other, url)
    logger.info(f"Will load selected model '{model_name}' on first generation request.")
    return True


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


def _contains_prompt_leak(text: str) -> bool:
    lowered = (text or "").lower()
    return any(re.search(pattern, lowered) for pattern in PROMPT_LEAK_PATTERNS)


def _clean_llm_response_text(text: str, concept: str) -> str:
    cleaned = clean_generic_filler(text, concept)
    cleaned = re.sub(r"\b(?:evaluation contract|contract role|source snippets|memory retention scenarios)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def build_category_generation_prompt(
    category: str,
    concept_str: str,
    npc_name: str,
    player_role: str = "player",
    subject: str = "history",
    concepts_str: str = "chronology or sources"
) -> str:
    """Backward-compatible category prompt helper used by tests and callers."""
    return {
        "identity": f"Write a very short first-person self-introduction for {npc_name}. Say who you are, directly answer what you do, name one focus related to {subject}, such as {concepts_str}, avoid generic storyteller language, and keep it to 1-2 sentences.",
        "teaching": f"Write a question from a {player_role} about '{concept_str}' and a direct answer. Answer directly, include one concrete fact or example from the reference doc, and add one practical implication for the player. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
        "dialogue": f"Write a casual turn about '{concept_str}' with an in-character answer. Answer directly, add one grounded detail or example, and include why it matters in play. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
        "quest": f"Write a challenge-style exchange about '{concept_str}' that stays practical and in character. Include one concrete action step, one example, and one decision-useful implication. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
        "refusal": f"Write an out-of-scope question for {npc_name}, state the boundary clearly, and redirect to a safe in-scope alternative. Do not add an unrelated fact or drift to another topic. Include 'Instead, I can help with...' plus one concrete in-scope topic related to {subject}, such as {concepts_str}. Keep it to 1-2 sentences.",
    }.get(category, f"Generate a concise educational dialogue about '{concept_str}' with one concrete detail.")


def _build_generation_prompt(
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


def clean_generic_filler(text: str, concept: str = "this topic") -> str:
    """Replace generic tutoring filler with a concept-specific sentence."""
    cleaned = text or ""
    for pattern in GENERIC_FILLER_REPLACEMENTS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    if cleaned.strip() == (text or "").strip() and any(
        phrase in cleaned.lower() for phrase in ["everything falls into place", "once you understand"]
    ):
        cleaned = re.sub(r"[^.!?]*(everything falls into place|once you understand)[^.!?]*[.!?]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned.split()) < 8:
        cleaned = f"For {concept}, focus on one concrete cause, effect, or example before connecting it to the bigger picture."
    return cleaned


def should_generate_multi_turn(category: str, index: int, ratio: float) -> bool:
    """Deterministically choose whether a row should be multi-turn."""
    if ratio <= 0:
        return False
    if ratio >= 1:
        return True
    bucket = int(hashlib.sha256(f"{category}:{index}".encode()).hexdigest()[:8], 16) % 10_000
    return bucket < int(ratio * 10_000)


def boost_examples_for_focus(examples_per_category: dict, focus_categories: list[str]) -> dict:
    """Boost counts for focused categories to support regeneration and auto-improvement."""
    result = dict(examples_per_category or {})
    for cat in list(result.keys()):
        if cat in (focus_categories or []):
            original = result[cat]
            result[cat] = max(original + 4, int(original * 2.0))
    return result


def stratified_train_val_split(examples: list[dict], val_split: float) -> tuple[list[dict], list[dict]]:
    """Split examples by category while preserving a validation example for each category."""
    if len(examples) <= 5:
        return examples, []

    by_category = defaultdict(list)
    for ex in examples:
        cat = ex.get("metadata", {}).get("category", "unknown")
        by_category[cat].append(ex)

    train_examples = []
    val_examples = []
    for cat, cat_examples in by_category.items():
        random.shuffle(cat_examples)
        if len(cat_examples) > 1:
            split = max(1, min(len(cat_examples) - 1, int(len(cat_examples) * val_split)))
        else:
            split = 0
        val_examples.extend(cat_examples[:split])
        train_examples.extend(cat_examples[split:])

    random.shuffle(train_examples)
    random.shuffle(val_examples)
    return train_examples, val_examples


class OllamaHealthCheck:
    """Verify Ollama is running and model is available."""
    
    def __init__(self, url="http://localhost:11434", timeout=5):
        self.url = url
        self.timeout = timeout
    
    def is_running(self) -> bool:
        """Check if Ollama service is responding."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=self.timeout)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama service not responding: {e}")
            return False
    
    def get_available_models(self) -> list[str]:
        """List all available local models."""
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return [m["name"].split(":")[0] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to fetch model list: {e}")
        return []
    
    def model_exists(self, model_name: str) -> bool:
        """Check if specific model is available."""
        models = self.get_available_models()
        return model_name in models
    
    def pull_model(self, model_name: str) -> bool:
        """Attempt to pull model from Ollama registry."""
        logger.info(f"Pulling model: {model_name} (this may take a few minutes)...")
        try:
            response = requests.post(
                f"{self.url}/api/pull",
                json={"name": model_name, "stream": False},
                timeout=600
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False


def _normalize_inference_server_url(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")


class OllamaGeneratorV2:
    """Enhanced Ollama generator with retry logic, batching, and progress tracking."""
    
    def __init__(self, model="llama2", url="http://localhost:11434/api/chat", 
                 max_retries=3, batch_size=4, health_check=None, inference_server_url: str | None = None):
        self.model = model
        self.url = url
        self.inference_server_url = _normalize_inference_server_url(
            inference_server_url or os.getenv("UCORE_INFERENCE_SERVER_URL")
        )
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.health_check = health_check or OllamaHealthCheck(url.rsplit("/api", 1)[0])
        self.request_count = 0
        self.error_count = 0
        self.success_count = 0
        
    def get_stats(self) -> dict:
        """Return generation statistics."""
        return {
            "requests": self.request_count,
            "successes": self.success_count,
            "errors": self.error_count,
            "success_rate": self.success_count / max(1, self.request_count)
        }

    def _build_payload(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        json_format: bool,
        stream: bool,
    ) -> dict:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_k": 40,
                "top_p": 0.9,
            },
        }
        if json_format:
            payload["format"] = "json"
        return payload

    @staticmethod
    def _extract_content(data: dict) -> str:
        return data.get("message", {}).get("content", "").strip()

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        return float(min(2 ** attempt, 8))

    def _retryable_errors(self):
        errors = [requests.exceptions.RequestException, json.JSONDecodeError, asyncio.TimeoutError]
        if aiohttp:
            errors.append(aiohttp.ClientError)
        return tuple(errors)

    def _post_chat(self, payload: dict) -> dict:
        target_url = f"{self.inference_server_url}/chat" if self.inference_server_url else self.url
        response = requests.post(target_url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    async def _post_chat_async(self, payload: dict, session):
        target_url = f"{self.inference_server_url}/chat" if self.inference_server_url else self.url
        async with session.post(target_url, json=payload, timeout=120) as response:
            response.raise_for_status()
            return await response.json()

    def _log_retry(self, attempt: int, reason: str):
        logger.warning(f"{reason} (attempt {attempt}/{self.max_retries})")

    def _log_unexpected_error(self, attempt: int, error: Exception):
        logger.error(f"Unexpected Ollama generation error (attempt {attempt}/{self.max_retries}): {error}")

    def _record_success(self, content: str) -> str:
        self.success_count += 1
        return content
    
    def generate(self, system_prompt: str, user_prompt: str, 
                temperature: float = 0.7, max_tokens: int = 512,
                json_format: bool = False, stream: bool = False) -> str | None:
        """Generate response with consolidated retry logic."""
        self.request_count += 1
        payload = self._build_payload(system_prompt, user_prompt, temperature, max_tokens, json_format, stream)

        for attempt in range(1, self.max_retries + 1):
            try:
                content = self._extract_content(self._post_chat(payload))
                if content:
                    return self._record_success(content)
                self._log_retry(attempt, "Empty response from Ollama")
            except self._retryable_errors() as exc:
                self._log_retry(attempt, f"{type(exc).__name__} from Ollama: {exc}")
            except Exception as exc:
                self._log_unexpected_error(attempt, exc)
                break

            if attempt < self.max_retries:
                time.sleep(self._retry_delay(attempt))

        self.error_count += 1
        logger.error(f"Failed to generate after {self.max_retries} attempts")
        return None
    
    async def generate_async(self, system_prompt: str, user_prompt: str,
                            temperature: float = 0.7, max_tokens: int = 512,
                            json_format: bool = False, session=None, executor=None) -> str | None:
        """Async generation wrapper."""
        if session and aiohttp:
            payload = self._build_payload(system_prompt, user_prompt, temperature, max_tokens, json_format, False)
            for attempt in range(1, self.max_retries + 1):
                try:
                    content = self._extract_content(await self._post_chat_async(payload, session))
                    if content:
                        return self._record_success(content)
                    self._log_retry(attempt, "Empty response from Ollama")
                except self._retryable_errors() as exc:
                    self._log_retry(attempt, f"{type(exc).__name__} from Ollama: {exc}")
                except Exception as exc:
                    self._log_unexpected_error(attempt, exc)
                    break

                if attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay(attempt))

            self.error_count += 1
            logger.error(f"Failed to generate after {self.max_retries} attempts")
            return None
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor,
                self.generate,
                system_prompt, user_prompt, temperature, max_tokens, json_format
            )

class ProgressTracker:
    """Track and report generation progress with ETA."""
    
    def __init__(self, total: int, report_interval: int = 5):
        self.total = total
        self.completed = 0
        self.report_interval = report_interval
        self.start_time = time.time()
        self.last_report_time = self.start_time
        self.errors = []
    
    def update(self, category: str = "", detail: str = ""):
        """Update progress counter."""
        self.completed += 1
        elapsed = time.time() - self.start_time
        
        if (time.time() - self.last_report_time) >= self.report_interval or self.completed == self.total:
            self._report_progress(category, detail, elapsed)
            self.last_report_time = time.time()
    
    def _report_progress(self, category: str, detail: str, elapsed: float):
        """Print progress with ETA."""
        pct = (self.completed / self.total * 100) if self.total > 0 else 0
        speed = self.completed / elapsed if elapsed > 0 else 0
        eta_sec = (self.total - self.completed) / speed if speed > 0 else 0
        
        eta_str = self._format_time(eta_sec)
        elapsed_str = self._format_time(elapsed)
        
        status = f"[{category}]" if category else ""
        logger.info(f"Progress: {self.completed}/{self.total} ({pct:.1f}%) "
                   f"| Elapsed: {elapsed_str} | ETA: {eta_str} {status}")
        
        if detail:
            logger.info(f"  {detail}")
    
    def add_error(self, category: str, concept: str, error: str):
        """Track generation errors."""
        self.errors.append({
            "category": category,
            "concept": concept,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"


from src.core.dataset.ollama_orchestrator import OllamaDatasetGenerator

def main():
    parser = argparse.ArgumentParser(
        description="Generate dataset using local Ollama model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./ucore generate-ollama subjects/NPC_specs/history_guide.json
  ./ucore generate-ollama subjects/NPC_specs/chemistry_instructor.json --model llama2 --batch-size 2
  ./ucore generate-ollama subjects/NPC_specs/fitness_coach.json --temperature 0.6 --check-health
        """
    )
    
    parser.add_argument("spec", help="Path to subject spec JSON")
    parser.add_argument(
        "--preset",
        default=None,
        choices=["generate-qwen25", "generate-llama31", "generate-qwen35-exp", "generate-qwen3-exp"],
        help="Named Ollama generation preset (default: generate-qwen25)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Exact Ollama model override (wins over --preset)",
    )
    parser.add_argument("--url", default="http://localhost:11434",
                       help="Ollama server URL (default: http://localhost:11434)")
    parser.add_argument("--inference-server-url", default=None,
                       help="Route generation through ucore inference-server /chat instead of direct Ollama")
    parser.add_argument("--output", "-o", default=None,
                       help="Output JSONL path")
    parser.add_argument("--batch-size", type=int, default=1,
                       help="Concurrent generation tasks (default: 1)")
    parser.add_argument("--max-retries", type=int, default=3,
                       help="Max retries per generation (default: 3)")
    parser.add_argument("--temperature", type=float, default=0.6,
                       help="Generation temperature (default: 0.6)")
    parser.add_argument("--multi-turn-ratio", type=float, default=0.25,
                       help="Fraction of rows to request as two-turn dialogues (default: 0.25)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed (default: 42)")
    parser.add_argument("--concept-focus", action="append", dest="concept_focus",
                       help="Focus regeneration on specific categories (repeatable, e.g. --concept-focus teaching --concept-focus dialogue)")
    parser.add_argument("--no-validation", action="store_true",
                       help="Skip validation split")
    parser.add_argument("--val-split", type=float, default=0.12,
                       help="Validation split ratio (default: 0.12)")
    parser.add_argument("--check-health", action="store_true",
                       help="Verify Ollama is running and model exists")
    parser.add_argument("--pull-model", action="store_true",
                       help="Auto-pull model if not found")
    parser.add_argument("--fresh", action="store_true",
                       help="Ignore checkpoint recovery and regenerate the dataset from scratch")
    parser.add_argument("--workflow-hooks", default=None,
                       help="Path to a JSONL hook log for step tracing (default: <output-dir>/workflow_hooks.jsonl)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Dry-run: show generation plan without generating")
    
    args = parser.parse_args()
    
    random.seed(args.seed)
    
    # ── Health check ───────────────────────────────────────────────────────
    health_checker = OllamaHealthCheck(url=args.url)
    
    logger.info("Checking Ollama health...")
    if not health_checker.is_running():
        logger.error("❌ Ollama is not running at " + args.url)
        logger.info("Start Ollama with: ollama serve")
        sys.exit(1)
    logger.info("✓ Ollama is running")
    
    # Get available models to help user select
    available = health_checker.get_available_models()
    if available:
        logger.info(f"Available models: {', '.join(available)}")
    
    resolved_model = resolve_ollama_model(preset=args.preset, model=args.model, role="generation")
    model_name = resolved_model.split(':')[0]  # Extract base model name for health checks
    if not health_checker.model_exists(model_name):
        if args.pull_model:
            logger.info(f"Model '{resolved_model}' not found, pulling...")
            if health_checker.pull_model(resolved_model):
                logger.info(f"✓ Model '{resolved_model}' pulled successfully")
            else:
                logger.error(f"Failed to pull model '{resolved_model}'")
                sys.exit(1)
        else:
            available = health_checker.get_available_models()
            logger.error(f"Model '{resolved_model}' not found")
            logger.info(f"Available models: {', '.join(available)}")
            logger.info("Use --pull-model to auto-pull, or install with: ollama pull <model>")
            sys.exit(1)
    
    if args.dry_run:
        logger.info("[DRY-RUN] Checking loaded Ollama models without modifying runtime...")
        ensure_selected_ollama_model_loaded(resolved_model, args.url, dry_run=True)
    else:
        logger.info("Ensuring selected Ollama model is isolated before generation...")
        ensure_selected_ollama_model_loaded(resolved_model, args.url)
        register_ollama_unload(resolved_model, args.url)
    
    # ── Load spec ──────────────────────────────────────────────────────────
    logger.info(f"Loading spec: {args.spec}")
    spec = load_subject_spec(args.spec)
    workflow = resolve_workflow_context(args.spec, spec=spec, technique="ollama")
    npc_key = workflow.npc_key
    technique = workflow.technique
    
    logger.info(f"Generating dataset for NPC: {spec['npc_name']}")
    logger.info(f"Subject: {spec['subject']}")
    logger.info(f"Model: {resolved_model}")
    
    output_path = args.output or paths.dataset_train_path(npc_key, technique)
    hook_recorder = WorkflowHookRecorder(
        args.workflow_hooks or default_hook_path(Path(output_path).parent),
        tool="generate_dataset_ollama",
        npc_key=npc_key,
        technique=technique,
        spec_path=args.spec,
        run_id=fallback_generation_run_id(npc_key, technique),
    )
    with hook_recorder.step("prepare", output_path=str(output_path), model=args.model):
        
        if args.dry_run:
            examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})
            if args.concept_focus:
                examples_per_category = boost_examples_for_focus(examples_per_category, args.concept_focus)
            examples_per_category = generation_request_counts_for_training_targets(
                examples_per_category,
                val_split=args.val_split,
                include_validation=not args.no_validation,
            )
            total = sum(examples_per_category.values())
            logger.info(f"\n[DRY-RUN] Would generate {total} examples with model '{resolved_model}':")
            for cat, count in examples_per_category.items():
                logger.info(f"  {cat:12s}: {count:3d} examples")
            if args.concept_focus:
                logger.info(f"  Focus categories: {', '.join(args.concept_focus)}")
            logger.info(f"\nTotal: {total} examples")
            logger.info(f"Temperature: {args.temperature}")
            logger.info(f"Batch size: {args.batch_size}")
            logger.info(f"Seed: {args.seed}\n")
            return
        # ── Generate dataset ──────────────────────────────────────────────────
        logger.info("Initializing generator...")
        with hook_recorder.step("model_health", model=resolved_model):
            generator = OllamaGeneratorV2(
                model=resolved_model,
                url=f"{args.url}/api/chat",
                max_retries=args.max_retries,
                batch_size=args.batch_size,
                health_check=health_checker,
                inference_server_url=args.inference_server_url,
            )
            dataset_gen = OllamaDatasetGenerator(spec, generator, batch_size=args.batch_size)
        
        examples_per_category = dict(spec.get("dataset", {}).get("examples_per_category", {}) or {})
        if args.concept_focus:
            examples_per_category = boost_examples_for_focus(examples_per_category, args.concept_focus)
        examples_per_category = generation_request_counts_for_training_targets(
            examples_per_category,
            val_split=args.val_split,
            include_validation=not args.no_validation,
        )

        total_to_gen = sum(examples_per_category.values())
        logger.info(f"Generating {total_to_gen} examples with model '{resolved_model}'...")
        if args.concept_focus:
            logger.info(f"Focused on categories: {', '.join(args.concept_focus)}")
        logger.info(f"This may take several minutes depending on hardware and model size\n")
        with hook_recorder.step("generate_examples", total_expected=total_to_gen, temperature=args.temperature, batch_size=args.batch_size):
            examples = dataset_gen.generate_dataset_sync(
                examples_per_category,
                temperature=args.temperature,
                multi_turn_ratio=args.multi_turn_ratio,
            )
        
        logger.info(f"\n{'='*70}")
        logger.info(f"Generation complete: {len(examples)} examples")
        stats = generator.get_stats()
        logger.info(f"Stats: {stats['successes']}/{stats['requests']} successful "
                   f"({stats['success_rate']*100:.1f}% success rate, {stats['errors']} errors)")
        logger.info(f"{'='*70}")
        
        # ── Train/validation split ─────────────────────────────────────────────
        if args.no_validation or len(examples) <= 5:
            train_examples = examples
            val_examples = []
        else:
            train_examples, val_examples = stratified_train_val_split(examples, args.val_split)
        
        # ── Write files ────────────────────────────────────────────────────────
        with hook_recorder.step("write_artifacts", output_path=str(output_path)):
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            val_path = None
            
            with open(output_path, "w") as f:
                for ex in train_examples:
                    ex["metadata"]["split"] = "train"
                    f.write(json.dumps(ex) + "\n")
            
            logger.info(f"✓ Wrote {len(train_examples)} training examples to {output_path}")
            
            if val_examples:
                val_path = output_path.parent / "validation.jsonl"
                with open(val_path, "w") as f:
                    for ex in val_examples:
                        ex["metadata"]["split"] = "validation"
                        f.write(json.dumps(ex) + "\n")
                logger.info(f"✓ Wrote {len(val_examples)} validation examples to {val_path}")
            
            # ── Write manifest ─────────────────────────────────────────────────────
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
            
            dataset_contract = dataset_contract_from_spec(spec)
            spec_hash = None
            try:
                spec_path_resolved = Path(args.spec)
                if spec_path_resolved.exists():
                    spec_hash = "sha256:" + hashlib.sha256(spec_path_resolved.read_bytes()).hexdigest()
            except Exception as e:
                pass

            manifest = {
                "npc_key": npc_key,
                "technique": "ollama",
                "model": args.model,
                "generation": {
                    "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "seed": args.seed,
                    "temperature": args.temperature,
                    "multi_turn_ratio": args.multi_turn_ratio,
                    "version": "ollama-v2",
                },
                "spec": {
                    "file": str(Path(args.spec).resolve()),
                    "hash": spec_hash,
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
                    "generator_stats": stats,
                },
            }
            
            manifest_path = output_path.parent / "train_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"✓ Wrote manifest to {manifest_path}")
            
            # ── Create versioned dataset directory ──
            from src.config.paths import dataset_version_dir, dataset_latest_symlink, generate_version_timestamp
            import shutil
            
            version = generate_version_timestamp()
            version_dir = dataset_version_dir(npc_key, technique, version)
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy files to versioned dir
            val_file = output_path.parent / "validation.jsonl"
            for src_file in [output_path, val_file, manifest_path]:
                if src_file.exists():
                    shutil.copy2(src_file, version_dir / src_file.name)
            
            # Update 'latest' symlink atomically
            latest_link = dataset_latest_symlink(npc_key, technique)
            latest_link.parent.mkdir(parents=True, exist_ok=True)
            tmp_link = latest_link.parent / ".latest_tmp"
            try:
                tmp_link.unlink(missing_ok=True)
                tmp_link.symlink_to(version_dir.name)
                tmp_link.rename(latest_link)
            except (OSError, FileNotFoundError) as e:
                logger.warning(f"Could not update 'latest' symlink: {e}")
        
        # ── Report errors ──────────────────────────────────────────────────────
        if dataset_gen.progress and dataset_gen.progress.errors:
            error_path = output_path.parent / "generation_errors.json"
            with open(error_path, "w") as f:
                json.dump(dataset_gen.progress.errors, f, indent=2)
            logger.warning(f"⚠ {len(dataset_gen.progress.errors)} generation errors logged to {error_path}")
        
        logger.info("\n✓ Dataset generation complete!")
        log_state("dataset_generated", npc_key=npc_key, total=len(examples),
                 train=len(train_examples), validation=len(val_examples), technique="ollama")


if __name__ == "__main__":
    main()
