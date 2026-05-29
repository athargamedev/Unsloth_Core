from __future__ import annotations

import atexit
import os
import subprocess
import threading
from dataclasses import dataclass
from urllib.parse import urlparse

import logging

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_REGISTERED_UNLOADS: dict[tuple[str, str], str] = {}
_ATEXIT_REGISTERED = False


@dataclass(frozen=True)
class OllamaEndpoint:
    host: str
    model: str


def _ollama_host_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.hostname:
        return "127.0.0.1:11434"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{parsed.hostname}:{port}"


def _run_ollama_cli(args: list[str], url: str):
    env = os.environ.copy()
    env["OLLAMA_HOST"] = _ollama_host_from_url(url)
    return subprocess.run(["ollama", *args], capture_output=True, text=True, env=env)


def parse_ollama_ps(output: str) -> list[str]:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return []
    if lines[0].lower().startswith("name"):
        lines = lines[1:]
    models: list[str] = []
    for line in lines:
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def list_running_ollama_models(url: str) -> list[str]:
    result = _run_ollama_cli(["ps"], url)
    if result.returncode != 0:
        logger.debug("Unable to query Ollama running models: %s", result.stderr.strip())
        return []
    return parse_ollama_ps(result.stdout)


def stop_ollama_model(model_name: str, url: str) -> bool:
    result = _run_ollama_cli(["stop", model_name], url)
    if result.returncode != 0:
        logger.debug("Failed to stop Ollama model '%s': %s", model_name, result.stderr.strip())
        return False
    logger.info("Stopped Ollama model: %s", model_name)
    return True


def stop_running_models(url: str, *, keep: set[str] | None = None) -> list[str]:
    keep = keep or set()
    stopped: list[str] = []
    for model in list_running_ollama_models(url):
        if model in keep:
            continue
        if stop_ollama_model(model, url):
            stopped.append(model)
    return stopped


def register_ollama_unload(model_name: str, url: str) -> None:
    """Register a best-effort ollama stop() at process exit."""
    global _ATEXIT_REGISTERED
    if not model_name:
        return
    key = (url, model_name)
    with _LOCK:
        _REGISTERED_UNLOADS.setdefault(key, model_name)
        if not _ATEXIT_REGISTERED:
            atexit.register(unload_registered_ollama_models)
            _ATEXIT_REGISTERED = True


def unload_registered_ollama_models() -> None:
    with _LOCK:
        items = list(_REGISTERED_UNLOADS.items())
        _REGISTERED_UNLOADS.clear()
    for (url, model_name), _label in items:
        try:
            stop_ollama_model(model_name, url)
        except Exception as e:
            continue


def ensure_selected_ollama_model_loaded(model_name: str, url: str, dry_run: bool = False) -> bool:
    running_models = list_running_ollama_models(url)
    if not running_models:
        logger.info("No Ollama model currently loaded.")
        return True

    if model_name in running_models:
        logger.info("Selected Ollama model '%s' is already loaded.", model_name)
        for other in [m for m in running_models if m != model_name]:
            if dry_run:
                logger.info("[DRY-RUN] Would stop loaded Ollama model: %s", other)
            else:
                stop_ollama_model(other, url)
        return True

    logger.info("Detected other Ollama model(s) loaded: %s", ", ".join(running_models))
    if dry_run:
        logger.info("[DRY-RUN] Would stop all loaded models and load '%s'", model_name)
        return True

    for other in running_models:
        stop_ollama_model(other, url)
    logger.info("Will load selected model '%s' on first generation request.", model_name)
    return True
