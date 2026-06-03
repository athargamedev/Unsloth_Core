from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from urllib.parse import urlparse

import requests

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None

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
    return subprocess.run(["ollama"] + args, capture_output=True, text=True, env=env)


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


class OllamaHealthCheck:
    def __init__(self, url="http://localhost:11434", timeout=5):
        self.url = url
        self.timeout = timeout

    def is_running(self) -> bool:
        try:
            return requests.get(f"{self.url}/api/tags", timeout=self.timeout).status_code == 200
        except Exception as e:
            logger.error(f"Ollama service not responding: {e}")
            return False

    def get_available_models(self) -> list[str]:
        try:
            response = requests.get(f"{self.url}/api/tags", timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return [m["name"].split(":")[0] for m in data.get("models", [])]
        except Exception as e:
            logger.error(f"Failed to fetch model list: {e}")
        return []

    def model_exists(self, model_name: str) -> bool:
        return model_name in self.get_available_models()

    def pull_model(self, model_name: str) -> bool:
        logger.info(f"Pulling model: {model_name} (this may take a few minutes)...")
        try:
            response = requests.post(f"{self.url}/api/pull", json={"name": model_name, "stream": False}, timeout=600)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False


class OllamaGeneratorV2:
    def __init__(self, model="llama2", url="http://localhost:11434/api/chat", max_retries=3, batch_size=4, health_check=None):
        self.model = model
        self.url = url
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.health_check = health_check or OllamaHealthCheck(url.rsplit("/api", 1)[0])
        self.request_count = 0
        self.error_count = 0
        self.success_count = 0

    def get_stats(self) -> dict:
        return {"requests": self.request_count, "successes": self.success_count, "errors": self.error_count, "success_rate": self.success_count / max(1, self.request_count)}

    def _build_payload(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int, json_format: bool, stream: bool) -> dict:
        payload = {"model": self.model, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], "stream": stream, "options": {"temperature": temperature, "num_predict": max_tokens, "top_k": 40, "top_p": 0.9}}
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
        response = requests.post(self.url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()

    async def _post_chat_async(self, payload: dict, session):
        async with session.post(self.url, json=payload, timeout=120) as response:
            response.raise_for_status()
            return await response.json()

    def _log_retry(self, attempt: int, reason: str):
        logger.warning(f"{reason} (attempt {attempt}/{self.max_retries})")

    def _log_unexpected_error(self, attempt: int, error: Exception):
        logger.error(f"Unexpected Ollama generation error (attempt {attempt}/{self.max_retries}): {error}")

    def _record_success(self, content: str) -> str:
        self.success_count += 1
        return content

    def generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 512, json_format: bool = False, stream: bool = False) -> str | None:
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

    async def generate_async(self, system_prompt: str, user_prompt: str, temperature: float = 0.7, max_tokens: int = 512, json_format: bool = False, session=None, executor=None) -> str | None:
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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(executor, self.generate, system_prompt, user_prompt, temperature, max_tokens, json_format)
