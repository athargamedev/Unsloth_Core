from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
from concurrent.futures import ThreadPoolExecutor

from src.core.dataset.generate_dataset import (
    ConceptExtractor,
    LLMGroundingVerifier,
    ReferenceDocRetriever,
    _refusal_user_message,
    compute_content_hash,
    generate_example_async,
)
from src.core.dataset.generation_profiles import (
    DialogueGuardrail,
    _is_history_subject,
    generate_dialogue_response,
    generate_identity_response,
    generate_quest_response,
    generate_refusal_response,
    generate_teaching_response,
)
from src.core.dataset.ollama_prompts import build_generation_prompt as _build_generation_prompt
from src.core.dataset.ollama_prompts import clean_generic_filler
from src.core.dataset.ollama_prompts import contains_prompt_leak as _contains_prompt_leak


def _clean_llm_response_text(text: str, concept: str) -> str:
    return clean_generic_filler(text, concept)


logger = logging.getLogger(__name__)


class OllamaDatasetGenerator:
    """High-level Ollama dataset generation orchestrator."""

    def __init__(
        self, spec: dict, generator: OllamaGeneratorV2, batch_size: int = 4, hook_recorder=None
    ):
        self.spec = spec
        self.generator = generator
        self.batch_size = batch_size
        self.hook_recorder = hook_recorder
        self.concepts = ConceptExtractor(spec).extract()
        self.retriever = ReferenceDocRetriever(spec.get("reference_doc"))
        self.guardrail = DialogueGuardrail()
        self.grounding_verifier = LLMGroundingVerifier()
        self.progress = None
        self.hook_recorder = hook_recorder

    def _emit_hook(self, step: str, status: str, **fields) -> None:
        if self.hook_recorder:
            self.hook_recorder.emit(step, status, **fields)

    def _pick_concept(self, category: str, index: int) -> str:
        """Cycle through concepts deterministically to maximize coverage."""
        if not self.concepts:
            return category
        category_offset = int(hashlib.sha256(category.encode("utf-8")).hexdigest()[:8], 16) % len(
            self.concepts
        )
        return str(self.concepts[(category_offset + index) % len(self.concepts)])

    def _infer_refusal_boundary(self, user_msg: str, concept_str: str) -> str:
        """Infer a refusal boundary label so fallback templates stay specific."""
        text = f"{user_msg} {concept_str}".lower()
        if any(
            k in text
            for k in [
                "medical",
                "dietary",
                "weight loss",
                "weight",
                "calorie",
                "nutrition",
                "condition",
            ]
        ):
            return "medical or dietary"
        if any(
            k in text
            for k in ["alien", "aliens", "extraterrestrial", "ufo", "life on other planets"]
        ):
            return "aliens or speculative claims"
        if any(
            k in text
            for k in ["exact date", "exact dates", "started and ended", "when did", "date range"]
        ):
            return "unsupported certainty or date range"
        if any(k in text for k in ["unsafe", "leave cooked", "food poisoning", "contamination"]):
            return "unsafe food preparation"
        if any(
            k in text
            for k in [
                "what if",
                "would have happened",
                "counterfactual",
                "hypothetical",
                "alternate history",
            ]
        ):
            return "speculate or counterfactual"
        if any(
            k in text
            for k in ["hiding", "conspiracy", "misinformation", "experts are hiding", "true story"]
        ):
            return "misinformation or conspiracy"
        if any(
            k in text
            for k in [
                "different topic",
                "something else",
                "leave world history aside",
                "talk about something else",
                "change the topic",
            ]
        ):
            return "topic change request"
        return "generic boundary"

    async def generate_example_llm(
        self,
        category: str,
        concept_str: str,
        difficulty: str = None,
        dialogue_type: str = None,
        scenario_name: str = None,
        boundary: str = None,
        session=None,
        executor=None,
        temperature: float = 0.7,
        multi_turn: bool = False,
    ) -> dict | None:
        """Generate single example using LLM."""
        npc_name = self.spec["npc_name"]
        system_prompt = self.spec["system_prompt"]

        game_context = self.spec.get("game_context") or {}
        setting = game_context.get("setting", "")
        relationship = game_context.get("relationship_to_player", "")

        dialogue_conf = self.spec.get("dialogue") or {}
        max_sentences = dialogue_conf.get("max_sentences", 3)
        max_chars = dialogue_conf.get("max_characters", 200)
        dialogue_conf.get("allow_formatting", True)
        player_archetypes = dialogue_conf.get("player_archetypes", ["player"])
        player_role = random.choice(player_archetypes) if player_archetypes else "player"

        grounding = ""
        if self.retriever and category not in ["identity", "refusal"]:
            contexts = self.retriever.get_grounding_context(concept_str, top_k=2)
            if contexts:
                grounding = "\nContext:\n" + "\n".join(contexts[:2])

        subject = self.spec.get("subject", "the subject")
        concepts = [c.get("name", "") for c in self.spec.get("concepts", [])]
        concepts_str = ", ".join(concepts[:3]) if concepts else f"topics related to {subject}"

        category_prompt = {
            "identity": f"Write a short self-introduction for {npc_name} in first person. Include one concrete topic you can help with related to {subject}, such as {concepts_str}.",
            "teaching": f"Write a question from a {player_role} about '{concept_str}' and a direct answer. Include one concrete grounded example and one practical implication. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
            "dialogue": f"Write a casual turn about '{concept_str}' with an in-character answer. Answer directly, include one grounded detail, and explain why it matters in play. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
            "quest": f"Write a challenge-style exchange about '{concept_str}' that stays practical and in character. Include one concrete action step, one example, and one decision-useful implication. Aim for 35-55 words when the NPC limits allow it; otherwise be as dense and specific as possible.",
            "refusal": f"Write an out-of-scope question for {npc_name}, mention the boundary, and a polite in-character refusal that directly acknowledges the topic change and offers another in-scope topic related to {subject}. Include both an explicit boundary phrase and a redirect phrase such as 'Instead, I can help with...'.",
        }.get(category, f"Generate a concise educational dialogue about '{concept_str}'.")
        if difficulty:
            category_prompt += f" Use a {difficulty} tone and prioritize clarity."
        if category == "dialogue" and dialogue_type:
            category_prompt += f" The exchange should feel like a {dialogue_type} dialogue."
        if category == "quest" and scenario_name:
            category_prompt += f" The quest should relate to '{scenario_name}'."
        if category == "refusal" and boundary:
            category_prompt += f" Focus on politely refusing requests about '{boundary}'."

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

        generation_prompt = _build_generation_prompt(
            npc_name=npc_name,
            system_prompt=system_prompt,
            setting=setting,
            relationship=relationship,
            category=category,
            concept_str=concept_str,
            category_prompt=category_prompt,
            grounding=grounding,
            player_role=player_role,
            max_sentences=max_sentences,
            max_chars=max_chars,
            multi_turn=multi_turn,
            turn_instruction=turn_instruction,
            json_shape=json_shape,
        )

        history_subject = _is_history_subject(self.spec)
        effective_temperature = min(temperature, 0.25) if history_subject else temperature

        self._emit_hook(
            "generate_example",
            "start",
            category=category,
            concept=concept_str,
            difficulty=difficulty,
            dialogue_type=dialogue_type,
            scenario_name=scenario_name,
            boundary=boundary,
            multi_turn=multi_turn,
        )

        async def fallback_template_example(reason: str) -> dict | None:
            fallback = await generate_example_async(
                self.spec,
                category,
                [concept_str],
                generator=None,
                temperature=temperature,
                difficulty=difficulty,
                dialogue_type=dialogue_type,
                scenario_name=scenario_name,
                boundary=boundary,
                seed=None,
                technique="ollama",
                session=session,
                executor=executor,
                retriever=self.retriever,
                guardrail=self.guardrail,
                checkpoint_store=None,
            )
            if fallback:
                logger.warning(
                    f"Falling back to deterministic template for {category}:{concept_str}"
                )
                self._emit_hook(
                    "generate_example",
                    "complete",
                    category=category,
                    concept=concept_str,
                    outcome="fallback",
                    reason=reason,
                )
            else:
                self._emit_hook(
                    "generate_example",
                    "error",
                    category=category,
                    concept=concept_str,
                    outcome="fallback",
                    reason=reason,
                )
            return fallback

        if history_subject:
            return await fallback_template_example("history_subject")

        response = await self.generator.generate_async(
            system_prompt="You are a training data generator for educational NPCs. Output valid JSON.",
            user_prompt=generation_prompt,
            temperature=effective_temperature,
            max_tokens=512,
            json_format=True,
            session=session,
            executor=executor,
        )

        if not response:
            return await fallback_template_example("empty_response")

        try:
            # Extract JSON from response (handle markdown code blocks)
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]

            res_json = json.loads(json_str.strip())
            user_msg = res_json.get("user", "").strip()
            asst_msg = _clean_llm_response_text(res_json.get("assistant", "").strip(), concept_str)
            user2_msg = res_json.get("user2", "").strip()
            asst2_msg = (
                _clean_llm_response_text(res_json.get("assistant2", "").strip(), concept_str)
                if res_json.get("assistant2")
                else ""
            )

            if category == "identity":
                asst_msg = generate_identity_response(self.spec)
            elif history_subject and category == "teaching":
                asst_msg = generate_teaching_response(
                    self.spec, concept_str, difficulty=difficulty, retriever=self.retriever
                )
            elif history_subject and category == "dialogue":
                asst_msg = generate_dialogue_response(
                    self.spec,
                    concept_str,
                    dialogue_type=dialogue_type or "deep_dive",
                    retriever=self.retriever,
                )
            elif history_subject and category == "quest":
                asst_msg = generate_quest_response(
                    self.spec, concept_str, scenario_name=scenario_name, retriever=self.retriever
                )

            if not user_msg or not asst_msg:
                return await fallback_template_example("parse_or_missing_fields")

            if _contains_prompt_leak(asst_msg):
                logger.warning(
                    "Prompt leak detected in LLM response; falling back to deterministic template"
                )
                return await fallback_template_example("parse_or_missing_fields")

            if len(asst_msg) > max_chars:
                logger.warning(
                    f"LLM response exceeded char limit ({len(asst_msg)} > {max_chars}); using fallback template"
                )
                return await fallback_template_example("parse_or_missing_fields")

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
                        return await fallback_template_example("parse_or_missing_fields")
                else:
                    return await fallback_template_example("parse_or_missing_fields")

            # Grounding verification with judge model
            if self.grounding_verifier._enabled and grounding:
                is_grounded, grounding_reason = self.grounding_verifier.verify(
                    asst_msg, [grounding]
                )
                if not is_grounded:
                    logger.warning(f"Grounding verification FAILED: {grounding_reason}")
                    return await fallback_template_example("grounding_failure")
            if category == "refusal":
                boundary_hint = self._infer_refusal_boundary(user_msg, concept_str)
                user_msg = _refusal_user_message(self.spec, boundary_hint)
                asst_msg = generate_refusal_response(self.spec, boundary=boundary_hint)
                user2_msg = ""
                asst2_msg = ""
                is_valid, reason = self.guardrail.validate(asst_msg, [grounding], self.spec)
                if not is_valid:
                    logger.warning(f"Refusal fallback rejected: {reason}")
                    return await fallback_template_example("parse_or_missing_fields")

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": asst_msg},
            ]
            if multi_turn and user2_msg and asst2_msg:
                is_valid2, reason2 = self.guardrail.validate(asst2_msg, [grounding], self.spec)
                if not is_valid2:
                    logger.warning(f"Guardrail rejection: {reason2}")
                    return await fallback_template_example("parse_or_missing_fields")
                messages.extend(
                    [
                        {"role": "user", "content": user2_msg},
                        {"role": "assistant", "content": asst2_msg},
                    ]
                )

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
                "retrieval_context": grounding.replace("\nContext:\n", "").strip().split("\n")
                if grounding
                else [],
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

            if self.hook_recorder:
                self.hook_recorder.emit(
                    "generate_example",
                    "complete",
                    category=category,
                    concept=concept_str,
                    outcome="generated",
                    multi_turn=bool(multi_turn and user2_msg and asst2_msg),
                )
            return {"messages": messages, "metadata": metadata}

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return await fallback_template_example("json_decode_error")

    async def generate_dataset_async(
        self,
        examples_per_category: dict,
        temperature: float = 0.6,
        max_workers: int = 4,
        multi_turn_ratio: float = 0.25,
        session=None,
        executor=None,
    ) -> list[dict]:
        """Generate dataset asynchronously."""
        from src.core.dataset.generate_dataset_ollama import (
            ProgressTracker,
            should_generate_multi_turn,
        )

        all_examples = []
        total_count = sum(examples_per_category.values())
        self.progress = ProgressTracker(total_count)
        allow_formatting = (self.spec.get("dialogue") or {}).get("allow_formatting", True)

        semaphore = asyncio.Semaphore(max_workers)

        async def gen_task(
            category: str,
            index: int,
            difficulty: str = None,
            dialogue_type: str = None,
            scenario_name: str = None,
            boundary: str = None,
        ):
            async with semaphore:
                try:
                    concept = self._pick_concept(category, index)
                    multi_turn = (
                        False
                        if category in {"identity", "refusal"}
                        else should_generate_multi_turn(category, index, multi_turn_ratio)
                    )
                    if not allow_formatting:
                        multi_turn = False
                    example = await self.generate_example_llm(
                        category,
                        str(concept),
                        difficulty=difficulty,
                        dialogue_type=dialogue_type,
                        scenario_name=scenario_name,
                        boundary=boundary,
                        session=session,
                        executor=executor,
                        temperature=temperature,
                        multi_turn=multi_turn,
                    )
                    if example:
                        all_examples.append(example)
                        self.progress.update(category, str(concept)[:50])
                    else:
                        self.progress.add_error(category, str(concept), "Generation returned None")
                except Exception as e:
                    self.progress.add_error(category, "unknown", str(e))
                    self._emit_hook(
                        "generate_example",
                        "error",
                        category=category,
                        concept=str(concept),
                        error=str(e),
                    )

        tasks = []
        for category, count in examples_per_category.items():
            difficulties = None
            dialogue_types = None
            scenario_names = None
            boundaries = None

            if category == "teaching":
                n_beg = int(count * 0.40)
                n_int = int(count * 0.35)
                n_adv = count - n_beg - n_int
                difficulties = (
                    ["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv
                )
                random.shuffle(difficulties)
            elif category == "dialogue":
                n_clar = int(count * 0.20)
                n_dive = int(count * 0.30)
                n_app = int(count * 0.30)
                n_misc = count - n_clar - n_dive - n_app
                dialogue_types = (
                    ["clarification"] * n_clar
                    + ["deep_dive"] * n_dive
                    + ["application"] * n_app
                    + ["misconception"] * n_misc
                )
                random.shuffle(dialogue_types)
                n_beg = int(count * 0.40)
                n_int = int(count * 0.35)
                n_adv = count - n_beg - n_int
                difficulties = (
                    ["beginner"] * n_beg + ["intermediate"] * n_int + ["advanced"] * n_adv
                )
                random.shuffle(difficulties)
            elif category == "quest":
                quest_scenarios = self.spec.get("quest_scenarios") or []
                if quest_scenarios:
                    scenario_names = [
                        quest_scenarios[i % len(quest_scenarios)] for i in range(count)
                    ]
                    random.shuffle(scenario_names)
                difficulties = ["intermediate"] * count
            elif category == "refusal":
                refusal_spec = self.spec.get("refusal", {})
                refusal_boundaries = refusal_spec.get("boundaries", []) or [
                    "medical or dietary",
                    "speculative claims",
                    "historical certainty",
                    "unsafe instructions",
                    "conspiracy or misinformation",
                ]
                boundaries = [refusal_boundaries[i % len(refusal_boundaries)] for i in range(count)]
                random.shuffle(boundaries)
                difficulties = ["beginner"] * count
            elif category == "identity":
                difficulties = ["beginner"] * count

            for i in range(count):
                diff = difficulties[i] if difficulties else None
                dt = dialogue_types[i] if dialogue_types else None
                sn = scenario_names[i] if scenario_names else None
                bd = boundaries[i] if boundaries else None
                tasks.append(gen_task(category, i, diff, dt, sn, bd))

        await asyncio.gather(*tasks)
        self._emit_hook(
            "generate_dataset",
            "complete",
            total_examples=len(all_examples),
            categories=list(examples_per_category.keys()),
        )
        return all_examples

    def generate_dataset_sync(
        self, examples_per_category: dict, temperature: float = 0.7, multi_turn_ratio: float = 0.25
    ) -> list[dict]:
        """Synchronous wrapper for async generation."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            with ThreadPoolExecutor(max_workers=self.batch_size) as executor:
                return asyncio.run(
                    self.generate_dataset_async(
                        examples_per_category,
                        temperature=temperature,
                        max_workers=self.batch_size,
                        multi_turn_ratio=multi_turn_ratio,
                        executor=executor,
                    )
                )
        raise RuntimeError("Synchronous dataset generation cannot run inside an active event loop.")
