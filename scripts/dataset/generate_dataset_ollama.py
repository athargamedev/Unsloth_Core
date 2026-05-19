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
import hashlib
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

try:
    import aiohttp
except ImportError:
    aiohttp = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SCRIPT_DIR))

from _config import paths, constants as C
from _config.log_setup import log_info, log_warn, log_error, log_state
from scripts.dataset_contracts import dataset_contract_from_spec, calculate_distribution_gaps
from generate_dataset import (
    CATEGORY_TEMPLATES,
    ConceptExtractor,
    ReferenceDocRetriever,
    DialogueGuardrail,
    generate_identity_response,
    generate_teaching_response,
    generate_dialogue_response,
    generate_quest_response,
    generate_refusal_response,
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


GENERIC_FILLER_REPLACEMENTS = [
    r"once you understand this, everything falls into place naturally\. ?",
    r"once you understand this, everything falls into place\. ?",
    r"the rest falls into place\. ?",
    r"let me tell you something about it\. ?",
]


def build_category_generation_prompt(category: str, concept_str: str, npc_name: str, player_role: str = "player") -> str:
    """Return category-specific instructions for Ollama dataset generation."""
    prompts = {
        "identity": (
            f"Create a natural user question asking who {npc_name} is and an immersive, in-character response."
        ),
        "teaching": (
            f"Create a question from the perspective of a {player_role} about '{concept_str}' and a helpful explanation."
        ),
        "dialogue": (
            f"Create a casual dialogue turn where the {player_role} asks or talks about '{concept_str}' and a helpful answer."
        ),
        "quest": (
            f"Create a dialogue turn where the {player_role} asks for or discusses a challenge or quest regarding '{concept_str}'."
        ),
        "refusal": (
            f"Create a question from the {player_role} that is out-of-scope for {npc_name} and a polite refusal in-character."
        ),
    }
    return prompts.get(category, f"Generate a concise educational dialogue about '{concept_str}'.")


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


class OllamaGeneratorV2:
    """Enhanced Ollama generator with retry logic, batching, and progress tracking."""
    
    def __init__(self, model="llama2", url="http://localhost:11434/api/chat", 
                 max_retries=3, batch_size=4, health_check=None):
        self.model = model
        self.url = url
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
    
    def generate(self, system_prompt: str, user_prompt: str, 
                temperature: float = 0.7, max_tokens: int = 512,
                json_format: bool = False, stream: bool = False) -> str | None:
        """Generate response with advanced retry logic."""
        self.request_count += 1
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "top_k": 40,
                "top_p": 0.9,
            }
        }
        
        if json_format:
            payload["format"] = "json"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(self.url, json=payload, timeout=120)
                response.raise_for_status()
                data = response.json()
                
                content = data.get("message", {}).get("content", "").strip()
                if content:
                    self.success_count += 1
                    return content
                else:
                    logger.warning(f"Empty response from Ollama (attempt {attempt}/{self.max_retries})")
                    
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt}/{self.max_retries} (retrying...)")
                time.sleep(2 ** attempt)  # Exponential backoff
                
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Connection error: {e}")
                return None
                
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON response on attempt {attempt}/{self.max_retries}")
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Generation error (attempt {attempt}/{self.max_retries}): {e}")
                if attempt < self.max_retries:
                    time.sleep(1)
        
        self.error_count += 1
        logger.error(f"Failed to generate after {self.max_retries} attempts")
        return None
    
    async def generate_async(self, system_prompt: str, user_prompt: str,
                            temperature: float = 0.7, max_tokens: int = 512,
                            json_format: bool = False, session=None, executor=None) -> str | None:
        """Async generation wrapper."""
        if session and aiohttp:
            return await self._generate_async_http(system_prompt, user_prompt, 
                                                   temperature, max_tokens, json_format, session)
        else:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor,
                self.generate,
                system_prompt, user_prompt, temperature, max_tokens, json_format
            )
    
    async def _generate_async_http(self, system_prompt: str, user_prompt: str,
                                   temperature: float, max_tokens: int, 
                                   json_format: bool, session):
        """Internal async HTTP generation."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        
        if json_format:
            payload["format"] = "json"
        
        try:
            async with session.post(self.url, json=payload, timeout=120) as response:
                response.raise_for_status()
                data = await response.json()
                content = data.get("message", {}).get("content", "").strip()
                if content:
                    self.success_count += 1
                    return content
        except Exception as e:
            logger.error(f"Async generation failed: {e}")
            self.error_count += 1
        
        return None


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


class OllamaDatasetGenerator:
    """High-level Ollama dataset generation orchestrator."""
    
    def __init__(self, spec: dict, generator: OllamaGeneratorV2, batch_size: int = 4):
        self.spec = spec
        self.generator = generator
        self.batch_size = batch_size
        self.concepts = ConceptExtractor(spec).extract()
        self.retriever = ReferenceDocRetriever(spec.get("reference_doc"))
        self.guardrail = DialogueGuardrail()
        self.progress = None
    
    def _pick_concept(self, category: str, index: int) -> str:
        """Cycle through concepts deterministically to maximize coverage."""
        if not self.concepts:
            return category
        category_offset = int(hashlib.sha256(category.encode("utf-8")).hexdigest()[:8], 16) % len(self.concepts)
        return str(self.concepts[(category_offset + index) % len(self.concepts)])

    def _infer_refusal_boundary(self, user_msg: str, concept_str: str) -> str:
        """Infer a refusal boundary label so fallback templates stay specific."""
        text = f"{user_msg} {concept_str}".lower()
        if any(k in text for k in ["medical", "dietary", "weight loss", "weight", "calorie", "nutrition", "condition"]):
            return "medical or dietary"
        if any(k in text for k in ["alien", "aliens", "extraterrestrial", "ufo", "life on other planets"]):
            return "aliens or speculative claims"
        if any(k in text for k in ["exact date", "exact dates", "started and ended", "when did", "date range"]):
            return "unsupported certainty or date range"
        if any(k in text for k in ["unsafe", "leave cooked", "food poisoning", "contamination"]):
            return "unsafe food preparation"
        if any(k in text for k in ["what if", "would have happened", "counterfactual", "hypothetical", "alternate history"]):
            return "speculate or counterfactual"
        if any(k in text for k in ["hiding", "conspiracy", "misinformation", "experts are hiding", "true story"]):
            return "misinformation or conspiracy"
        return "generic boundary"

    async def generate_example_llm(self, category: str, concept_str: str, 
                                    difficulty: str = None, dialogue_type: str = None,
                                    scenario_name: str = None, boundary: str = None,
                                    session=None, executor=None, temperature: float = 0.7,
                                    multi_turn: bool = False) -> dict | None:
        """Generate single example using LLM."""
        npc_name = self.spec["npc_name"]
        system_prompt = self.spec["system_prompt"]
        
        game_context = self.spec.get("game_context") or {}
        setting = game_context.get("setting", "")
        relationship = game_context.get("relationship_to_player", "")

        dialogue_conf = self.spec.get("dialogue") or {}
        max_sentences = dialogue_conf.get("max_sentences", 3)
        max_chars = dialogue_conf.get("max_characters", 200)
        player_archetypes = dialogue_conf.get("player_archetypes", ["player"])
        player_role = random.choice(player_archetypes) if player_archetypes else "player"

        grounding = ""
        if self.retriever and category not in ["identity", "refusal"]:
            contexts = self.retriever.get_grounding_context(concept_str, top_k=2)
            if contexts:
                grounding = "\nContext:\n" + "\n".join(contexts[:2])
        
        category_prompt = build_category_generation_prompt(category, concept_str, npc_name, player_role)
        turn_instruction = ""
        json_shape = f'  "user": "user message as a {player_role} (1-2 sentences)",\n  "assistant": "NPC response (1-{max_sentences} sentences, max {max_chars} chars, in character)"'
        if multi_turn:
            turn_instruction = "\nMake this a two-turn exchange: first answer, then a brief follow-up question and answer."
            json_shape = (
                f'  "user": "first user message as a {player_role}",\n'
                f'  "assistant": "first NPC response (1-{max_sentences} sentences, max {max_chars} chars)",\n'
                f'  "user2": "follow-up user message as a {player_role}",\n'
                f'  "assistant2": "second NPC response (1-{max_sentences} sentences, max {max_chars} chars)"'
            )
        
        generation_prompt = f"""Generate a training dialogue in JSON format for NPC '{npc_name}'.

System Prompt: {system_prompt}
Setting: {setting or 'Not specified'}
Player Relationship: {relationship or 'Not specified'}

Task: {category_prompt}{turn_instruction}
Category: {category}
Concept: {concept_str}{grounding}

Instructions:
- The user message must sound like an in-game player ({player_role}).
- The assistant response must follow {npc_name}'s system prompt perfectly.
- Speak 1-{max_sentences} sentences (MAXIMUM {max_chars} characters).
- NEVER use markdown lists, bullet points, bolding, or tables (keep text clean for game UI).
- Never mention being an AI or language model.

Return JSON:
{{
{json_shape}
}}
"""
        
        response = await self.generator.generate_async(
            system_prompt="You are a training data generator for educational NPCs. Output valid JSON.",
            user_prompt=generation_prompt,
            temperature=temperature,
            max_tokens=512,
            json_format=True,
            session=session,
            executor=executor
        )
        
        if not response:
            return None
        
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            
            res_json = json.loads(json_str.strip())
            user_msg = res_json.get("user", "").strip()
            asst_msg = clean_generic_filler(res_json.get("assistant", "").strip(), concept_str)
            user2_msg = res_json.get("user2", "").strip()
            asst2_msg = clean_generic_filler(res_json.get("assistant2", "").strip(), concept_str) if res_json.get("assistant2") else ""
            
            if not user_msg or not asst_msg:
                return None
            
            # Validate with guardrail
            is_valid, reason = self.guardrail.validate(asst_msg, [grounding], self.spec)
            if not is_valid:
                logger.warning(f"Guardrail rejection: {reason}")
                if category == "refusal":
                    boundary_hint = self._infer_refusal_boundary(user_msg, concept_str)
                    asst_msg = generate_refusal_response(self.spec, boundary=boundary_hint)
                    is_valid, reason = self.guardrail.validate(asst_msg, [grounding], self.spec)
                    if not is_valid:
                        logger.warning(f"Refusal fallback rejected: {reason}")
                        return None
                else:
                    return None
            if category == "refusal":
                boundary_hint = self._infer_refusal_boundary(user_msg, concept_str)
                user_msg = _refusal_user_message(self.spec, boundary_hint)
                asst_msg = generate_refusal_response(self.spec, boundary=boundary_hint)
                user2_msg = ""
                asst2_msg = ""
                is_valid, reason = self.guardrail.validate(asst_msg, [grounding], self.spec)
                if not is_valid:
                    logger.warning(f"Refusal fallback rejected: {reason}")
                    return None
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": asst_msg}
            ]
            if multi_turn and user2_msg and asst2_msg:
                is_valid2, reason2 = self.guardrail.validate(asst2_msg, [grounding], self.spec)
                if not is_valid2:
                    logger.warning(f"Guardrail rejection: {reason2}")
                    return None
                messages.extend([
                    {"role": "user", "content": user2_msg},
                    {"role": "assistant", "content": asst2_msg},
                ])
            
            content_hash = compute_content_hash(messages)
            metadata = {
                "npc_key": self.spec["npc_key"],
                "category": category,
                "technique": "ollama",
                "source": f"ollama:{self.generator.model}",
                "split": "train",
                "concept": concept_str,
                "difficulty": difficulty,
                "safety_tags": ["boundary_enforcement"] if category == "refusal" else [],
                "content_hash": content_hash,
                "generator_params": {
                    "temperature": temperature,
                    "model": self.generator.model,
                    "multi_turn": bool(multi_turn and user2_msg and asst2_msg),
                    "turn_count": 2 if multi_turn and user2_msg and asst2_msg else 1,
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
                "metadata": metadata
            }
        
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None
    
    async def generate_dataset_async(self, examples_per_category: dict, 
                                    temperature: float = 0.7, max_workers: int = 4,
                                    multi_turn_ratio: float = 0.25,
                                    session=None, executor=None) -> list[dict]:
        """Generate dataset asynchronously."""
        all_examples = []
        total_count = sum(examples_per_category.values())
        self.progress = ProgressTracker(total_count)
        
        semaphore = asyncio.Semaphore(max_workers)
        
        async def gen_task(category: str, index: int, difficulty: str = None):
            async with semaphore:
                try:
                    concept = self._pick_concept(category, index)
                    multi_turn = False if category in {"identity", "refusal"} else should_generate_multi_turn(category, index, multi_turn_ratio)
                    example = await self.generate_example_llm(
                        category, str(concept), difficulty=difficulty,
                        session=session, executor=executor, temperature=temperature,
                        multi_turn=multi_turn,
                    )
                    if example:
                        all_examples.append(example)
                        self.progress.update(category, str(concept)[:50])
                    else:
                        self.progress.add_error(category, str(concept), "Generation returned None")
                except Exception as e:
                    self.progress.add_error(category, "unknown", str(e))
        
        tasks = []
        for category, count in examples_per_category.items():
            if category == "teaching":
                for i in range(count):
                    diffs = ["beginner"] * int(count * 0.4) + ["intermediate"] * int(count * 0.35) + ["advanced"] * int(count * 0.25)
                    diff = diffs[i % len(diffs)] if diffs else None
                    tasks.append(gen_task(category, i, diff))
            else:
                for i in range(count):
                    tasks.append(gen_task(category, i))
        
        await asyncio.gather(*tasks)
        return all_examples
    
    def generate_dataset_sync(self, examples_per_category: dict, 
                             temperature: float = 0.7,
                             multi_turn_ratio: float = 0.25) -> list[dict]:
        """Synchronous wrapper for async generation."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
            examples = loop.run_until_complete(
                self.generate_dataset_async(
                    examples_per_category,
                    temperature=temperature,
                    max_workers=self.batch_size,
                    multi_turn_ratio=multi_turn_ratio,
                    executor=executor
                )
            )
        
        return examples


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
    parser.add_argument("--model", default="qwen2.5:7b", 
                       help="Ollama model to use (default: qwen2.5:7b)")
    parser.add_argument("--url", default="http://localhost:11434",
                       help="Ollama server URL (default: http://localhost:11434)")
    parser.add_argument("--output", "-o", default=None,
                       help="Output JSONL path")
    parser.add_argument("--batch-size", type=int, default=4,
                       help="Concurrent generation tasks (default: 4)")
    parser.add_argument("--max-retries", type=int, default=3,
                       help="Max retries per generation (default: 3)")
    parser.add_argument("--temperature", type=float, default=0.7,
                       help="Generation temperature (default: 0.7)")
    parser.add_argument("--multi-turn-ratio", type=float, default=0.25,
                       help="Fraction of rows to request as two-turn dialogues (default: 0.25)")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed (default: 42)")
    parser.add_argument("--no-validation", action="store_true",
                       help="Skip validation split")
    parser.add_argument("--val-split", type=float, default=0.12,
                       help="Validation split ratio (default: 0.12)")
    parser.add_argument("--check-health", action="store_true",
                       help="Verify Ollama is running and model exists")
    parser.add_argument("--pull-model", action="store_true",
                       help="Auto-pull model if not found")
    parser.add_argument("--dry-run", action="store_true",
                       help="Dry-run: show generation plan without generating")
    
    args = parser.parse_args()
    
    random.seed(args.seed)
    
    # ── Health check ───────────────────────────────────────────────────────
    health_checker = OllamaHealthCheck(url=args.url)
    
    if args.check_health or args.pull_model:
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
        
        model_name = args.model.split(':')[0]  # Extract base model name (qwen2.5 from qwen2.5:7b)
        if not health_checker.model_exists(model_name):
            if args.pull_model:
                logger.info(f"Model '{args.model}' not found, pulling...")
                if health_checker.pull_model(args.model):
                    logger.info(f"✓ Model '{args.model}' pulled successfully")
                else:
                    logger.error(f"Failed to pull model '{args.model}'")
                    sys.exit(1)
            else:
                available = health_checker.get_available_models()
                logger.error(f"Model '{args.model}' not found")
                logger.info(f"Available models: {', '.join(available)}")
                logger.info("Use --pull-model to auto-pull, or install with: ollama pull <model>")
                sys.exit(1)
    
    # ── Load spec ──────────────────────────────────────────────────────────
    logger.info(f"Loading spec: {args.spec}")
    spec = load_subject_spec(args.spec)
    npc_key = spec["npc_key"]
    
    logger.info(f"Generating dataset for NPC: {spec['npc_name']}")
    logger.info(f"Subject: {spec['subject']}")
    logger.info(f"Model: {args.model}")
    
    output_path = args.output or paths.dataset_train_path(npc_key, "ollama")
    
    if args.dry_run:
        examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})
        total = sum(examples_per_category.values())
        logger.info(f"\n[DRY-RUN] Would generate {total} examples with model '{args.model}':")
        for cat, count in examples_per_category.items():
            logger.info(f"  {cat:12s}: {count:3d} examples")
        logger.info(f"\nTotal: {total} examples")
        logger.info(f"Temperature: {args.temperature}")
        logger.info(f"Batch size: {args.batch_size}")
        logger.info(f"Seed: {args.seed}\n")
        return
    
    # ── Generate dataset ──────────────────────────────────────────────────
    logger.info("Initializing generator...")
    generator = OllamaGeneratorV2(
        model=args.model,
        url=f"{args.url}/api/chat",
        max_retries=args.max_retries,
        batch_size=args.batch_size,
        health_check=health_checker
    )
    
    dataset_gen = OllamaDatasetGenerator(spec, generator, batch_size=args.batch_size)
    
    examples_per_category = spec.get("dataset", {}).get("examples_per_category", {})
    
    total_to_gen = sum(examples_per_category.values())
    logger.info(f"Generating {total_to_gen} examples with model '{args.model}'...")
    logger.info(f"This may take several minutes depending on hardware and model size\n")
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
        val_count = max(1, int(len(examples) * args.val_split))
        random.shuffle(examples)
        val_examples = examples[:val_count]
        train_examples = examples[val_count:]
    
    # ── Write files ────────────────────────────────────────────────────────
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
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
    
    for ex in examples:
        meta = ex.get("metadata", {})
        by_category[meta.get("category", "unknown")] += 1
        diff = meta.get("difficulty")
        if diff:
            by_difficulty[diff] += 1
    
    dataset_contract = dataset_contract_from_spec(spec)
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
            "generator_stats": stats,
        },
    }
    
    manifest_path = output_path.parent / "train_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    logger.info(f"✓ Wrote manifest to {manifest_path}")
    
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
