"""Shared DeepEval metrics for generated NPC training datasets."""

import os
from typing import Optional, Tuple, Union

from deepeval.metrics import (
    AnswerRelevancyMetric,
    BiasMetric,
    ContextualRelevancyMetric,
    ConversationCompletenessMetric,
    FaithfulnessMetric,
    GEval,
    HallucinationMetric,
    KnowledgeRetentionMetric,
    RoleAdherenceMetric,
    ToxicityMetric,
)
from deepeval.models import DeepEvalBaseLLM, OllamaModel
from deepeval.models.llms.ollama_model import retry_ollama

from scripts.ops.ollama_lifecycle import register_ollama_unload
from scripts.ops.wandb_inference import DEFAULT_WANDB_INFERENCE_MODEL, WandbInferenceClient
from deepeval.test_case import SingleTurnParams
from pydantic import BaseModel


def _ollama_think_enabled() -> bool:
    return os.getenv("DEEPEVAL_OLLAMA_THINK", "false").strip().lower() in {"1", "true", "yes", "on"}


class DatasetJudgeOllamaModel(OllamaModel):
    """DeepEval Ollama judge with explicit control over thinking models."""

    def __init__(self, *args, think: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.think = think

    def _chat_kwargs(self, prompt: str, schema: Optional[type[BaseModel]]) -> dict:
        return {
            "model": self.name,
            "messages": [{"role": "user", "content": prompt}],
            "format": schema.model_json_schema() if schema else None,
            "options": {
                "temperature": self.temperature,
                **self.generation_kwargs,
            },
            "think": self.think,
        }

    @retry_ollama
    def generate(
        self, prompt: str, schema: Optional[type[BaseModel]] = None
    ) -> Tuple[Union[str, BaseModel], float]:
        response = self.load_model().chat(**self._chat_kwargs(prompt, schema))
        return (
            schema.model_validate_json(response.message.content)
            if schema
            else response.message.content,
            0,
        )

    @retry_ollama
    async def a_generate(
        self, prompt: str, schema: Optional[type[BaseModel]] = None
    ) -> Tuple[Union[str, BaseModel], float]:
        response = await self.load_model(async_mode=True).chat(**self._chat_kwargs(prompt, schema))
        return (
            schema.model_validate_json(response.message.content)
            if schema
            else response.message.content,
            0,
        )


def _ollama_judge() -> DatasetJudgeOllamaModel:
    return DatasetJudgeOllamaModel(
        model=os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b"),
        base_url=os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=float(os.getenv("DEEPEVAL_OLLAMA_TEMPERATURE", "0")),
        think=_ollama_think_enabled(),
    )


class DatasetJudgeWandbInferenceModel(DeepEvalBaseLLM):
    """DeepEval judge backed by W&B Serverless Inference."""

    def __init__(self, model: str | None = None, temperature: float = 0.0):
        self.temperature = temperature
        super().__init__(model=model or DEFAULT_WANDB_INFERENCE_MODEL)

    def load_model(self, *args, **kwargs):
        return WandbInferenceClient(
            model=self.name,
            entity=os.getenv("DEEPEVAL_WANDB_ENTITY") or os.getenv("WANDB_ENTITY"),
            project=os.getenv("DEEPEVAL_WANDB_PROJECT") or os.getenv("WANDB_PROJECT"),
            temperature=self.temperature,
        )

    def get_model_name(self, *args, **kwargs) -> str:
        return f"wandb-inference:{self.name}"

    def _messages(self, prompt: str, schema: Optional[type[BaseModel]] = None) -> list[dict[str, str]]:
        if schema is None:
            return [{"role": "user", "content": prompt}]
        return [
            {
                "role": "system",
                "content": "Return only a JSON object matching the requested schema. Do not include markdown.",
            },
            {"role": "user", "content": f"{prompt}\n\nJSON schema:\n{schema.model_json_schema()}"},
        ]

    def generate(self, prompt: str, schema: Optional[type[BaseModel]] = None):
        content = self.model.chat(
            self._messages(prompt, schema),
            response_format={"type": "json_object"} if schema else None,
        )
        return (schema.model_validate_json(content) if schema else content, 0)

    async def a_generate(self, prompt: str, schema: Optional[type[BaseModel]] = None):
        content = await self.model.achat(
            self._messages(prompt, schema),
            response_format={"type": "json_object"} if schema else None,
        )
        return (schema.model_validate_json(content) if schema else content, 0)


def _wandb_judge() -> DatasetJudgeWandbInferenceModel:
    return DatasetJudgeWandbInferenceModel(
        model=os.getenv("DEEPEVAL_WANDB_MODEL", DEFAULT_WANDB_INFERENCE_MODEL),
        temperature=float(os.getenv("DEEPEVAL_WANDB_TEMPERATURE", "0")),
    )


if os.getenv("DEEPEVAL_JUDGE_PROVIDER", "ollama").strip().lower() == "wandb":
    JUDGE_MODEL = _wandb_judge()
else:
    JUDGE_MODEL = _ollama_judge()
    register_ollama_unload(
        os.getenv("DEEPEVAL_OLLAMA_MODEL", "qwen2.5:7b"),
        os.getenv("DEEPEVAL_OLLAMA_BASE_URL", "http://localhost:11434"),
    )

DATASET_QUALITY_METRICS = [
    GEval(
        name="Persona and Category Fit",
        criteria=(
            "Score whether the assistant response fits the NPC system prompt, "
            "the requested training category, and the user message. Penalize "
            "AI disclaimers, off-topic answers, unsafe boundary handling, "
            "responses longer than the NPC max sentence rule, or responses "
            "that ignore the category metadata. Severely penalize responses "
            "that use markdown formatting (like ## headers or bullet points) "
            "when forbidden by the prompt. Severely penalize responses that "
            "are too short or lack detail if the prompt requests descriptive answers."
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
    ContextualRelevancyMetric(model=JUDGE_MODEL, threshold=0.75, async_mode=True),
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
