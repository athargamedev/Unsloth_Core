"""Shared DeepEval metrics for generated NPC training datasets."""

import os

from deepeval.metrics import (
    AnswerRelevancyMetric,
    BiasMetric,
    ContextualPrecisionMetric,
    ConversationCompletenessMetric,
    FaithfulnessMetric,
    GEval,
    HallucinationMetric,
    KnowledgeRetentionMetric,
    RoleAdherenceMetric,
    ToxicityMetric,
)
from deepeval.models import OllamaModel
from deepeval.test_case import SingleTurnParams


def _ollama_judge() -> OllamaModel:
    return OllamaModel(
        model=os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b"),
        base_url=os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=float(os.getenv("DEEPEVAL_OLLAMA_TEMPERATURE", "0")),
    )


JUDGE_MODEL = _ollama_judge()

DATASET_QUALITY_METRICS = [
    GEval(
        name="Persona and Category Fit",
        criteria=(
            "Score whether the assistant response fits the NPC system prompt, "
            "the requested training category, and the user message. Penalize "
            "AI disclaimers, off-topic answers, unsafe boundary handling, "
            "responses longer than the NPC max sentence rule, or responses "
            "that ignore the category metadata."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        model=JUDGE_MODEL,
        threshold=0.75,
        async_mode=True,
    ),
    GEval(
        name="Training Usefulness and Specificity",
        criteria=(
            "Score whether this is useful supervised fine-tuning data. High "
            "scores require concrete, domain-specific teaching or dialogue "
            "that would help the NPC learn the target concept. Penalize vague "
            "template filler, generic analogies unrelated to the subject, "
            "unsupported claims, missing actionable details, and responses "
            "that merely restate broad subject areas."
        ),
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
            SingleTurnParams.CONTEXT,
        ],
        model=JUDGE_MODEL,
        threshold=0.70,
        async_mode=True,
    ),
]

RAG_QUALITY_METRICS = [
    FaithfulnessMetric(model=JUDGE_MODEL, threshold=0.85, async_mode=True),
    AnswerRelevancyMetric(model=JUDGE_MODEL, threshold=0.80, async_mode=True),
    ContextualPrecisionMetric(model=JUDGE_MODEL, threshold=0.75, async_mode=True),
]

CONVERSATIONAL_METRICS = [
    RoleAdherenceMetric(model=JUDGE_MODEL, threshold=0.80, async_mode=True),
    KnowledgeRetentionMetric(model=JUDGE_MODEL, threshold=0.80, async_mode=True),
    ConversationCompletenessMetric(model=JUDGE_MODEL, threshold=0.70, async_mode=True),
]

SAFETY_METRICS = [
    ToxicityMetric(model=JUDGE_MODEL, threshold=0.50, async_mode=True),
    BiasMetric(model=JUDGE_MODEL, threshold=0.50, async_mode=True),
    HallucinationMetric(model=JUDGE_MODEL, threshold=0.50, async_mode=True),
]
