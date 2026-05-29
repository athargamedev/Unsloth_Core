"""Small OpenAI-compatible client helpers for W&B Serverless Inference."""

from __future__ import annotations

import asyncio
import json
import netrc
import os
import re
from pathlib import Path
from typing import Any

import requests

WANDB_INFERENCE_BASE_URL = "https://api.inference.wandb.ai/v1"
DEFAULT_WANDB_INFERENCE_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
DEFAULT_WANDB_ENTITY = "andreabenathar-twl-games"
DEFAULT_WANDB_PROJECT = "unsloth-core"


def wandb_api_key() -> str | None:
    """Resolve a W&B API key from env or ~/.netrc without printing it."""
    key = os.getenv("WANDB_API_KEY")
    if key:
        return key
    try:
        auth = netrc.netrc(str(Path.home() / ".netrc")).authenticators("api.wandb.ai")
    except Exception as e:
        auth = None
    if auth and auth[2]:
        return auth[2]
    return None


def wandb_inference_project(entity: str | None = None, project: str | None = None) -> str:
    entity = entity or os.getenv("WANDB_ENTITY") or os.getenv("DEEPEVAL_WANDB_ENTITY") or DEFAULT_WANDB_ENTITY
    project = project or os.getenv("WANDB_PROJECT") or os.getenv("DEEPEVAL_WANDB_PROJECT") or DEFAULT_WANDB_PROJECT
    return f"{entity}/{project}"


def extract_json_object(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class WandbInferenceClient:
    """Minimal W&B Serverless Inference chat-completions client."""

    def __init__(
        self,
        *,
        model: str = DEFAULT_WANDB_INFERENCE_MODEL,
        entity: str | None = None,
        project: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: int = 120,
        temperature: float = 0.0,
    ) -> None:
        self.model = model
        self.base_url = (base_url or os.getenv("WANDB_INFERENCE_BASE_URL") or WANDB_INFERENCE_BASE_URL).rstrip("/")
        self.api_key = api_key or wandb_api_key()
        self.project = wandb_inference_project(entity, project)
        self.timeout = timeout
        self.temperature = temperature
        if not self.api_key:
            raise RuntimeError("W&B Inference requires WANDB_API_KEY or ~/.netrc credentials for api.wandb.ai")

    def chat(self, messages: list[dict[str, str]], *, response_format: dict[str, Any] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if response_format:
            payload["response_format"] = response_format
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "OpenAI-Project": self.project,
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "")

    async def achat(self, messages: list[dict[str, str]], *, response_format: dict[str, Any] | None = None) -> str:
        return await asyncio.to_thread(self.chat, messages, response_format=response_format)


def wandb_inference_available() -> bool:
    return bool(wandb_api_key())
