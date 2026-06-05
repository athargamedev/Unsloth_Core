#!/usr/bin/env python3
"""Lightweight local inference control plane for Unsloth_Core.

Provides a tiny stdlib HTTP server over Ollama with stable endpoints:
/status, /warm, /judge, /unload. The core service is injectable so unit tests do
not depend on live Ollama state.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.ops.gpu_lease import GpuLeaseManager, LeaseConflictError  # noqa: E402
from src.core.ops.ollama_lifecycle import (  # noqa: E402
    list_running_ollama_models,
    stop_ollama_model,
    stop_running_models,
)
from src.core.ops.ollama_model_presets import resolve_ollama_model  # noqa: E402

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_JUDGE_RUBRIC = """
Classify the quality of this NPC response.

CONTEXT:
{context}

USER QUESTION:
{input}

NPC RESPONSE:
{actual_output}

Return JSON with:
{{
  "is_high_quality": bool,
  "failure_reason": string|null,
  "score": float
}}
""".strip()


@dataclass
class InferenceServerConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    ollama_host: str = DEFAULT_OLLAMA_HOST
    default_model: str | None = None
    timeout: int = 180


class OllamaHTTPClient:
    """Small Ollama client using stdlib urllib for server-control paths."""

    def __init__(self, host: str = DEFAULT_OLLAMA_HOST, timeout: int = 180) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        tags = self._request("GET", "/api/tags", timeout=15)
        models = [
            m.get("name") for m in tags.get("models", []) if isinstance(m, dict) and m.get("name")
        ]
        return {
            "ok": True,
            "models": models,
            "running_models": list_running_ollama_models(self.host),
        }

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        format: str | None = None,
        options: dict[str, Any] | None = None,
        keep_alive: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        if format:
            payload["format"] = format
        if options:
            payload["options"] = options
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return self._request("POST", "/api/chat", payload=payload, timeout=timeout or self.timeout)

    def unload(self, model: str | None = None) -> list[str]:
        if model:
            return [model] if stop_ollama_model(model, self.host) else []
        return stop_running_models(self.host)

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(
            self.host + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=timeout or self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Ollama HTTP {exc.code}: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Ollama unavailable at {self.host}: {exc.reason}") from exc


class InferenceService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        default_model: str | None = None,
        timeout: int = 180,
        lease_manager: GpuLeaseManager | None = None,
    ) -> None:
        self.client = client or OllamaHTTPClient(timeout=timeout)
        self.default_model = default_model or resolve_ollama_model(role="judge")
        self.timeout = timeout
        self.lease_manager = lease_manager or GpuLeaseManager()

    def status(self) -> dict[str, Any]:
        backend_status = self.client.status()
        return {
            "ok": bool(backend_status.get("ok", True)),
            "backend": "ollama",
            "default_model": self.default_model,
            "models": backend_status.get("models", []),
            "running_models": backend_status.get("running_models", []),
            "gpu_lease": self.lease_manager.status(),
        }

    def lease(self, payload: dict[str, Any]) -> dict[str, Any]:
        mode = payload.get("mode", "")
        ttl = int(payload.get("ttl", 300))
        try:
            lease = self.lease_manager.request_lease(mode, ttl=ttl)
            return {"ok": True, "lease": lease.as_dict()}
        except (ValueError, LeaseConflictError) as exc:
            return {"ok": False, "error": str(exc)}

    def release(self, payload: dict[str, Any]) -> dict[str, Any]:
        lease_id = payload.get("lease_id", "")
        return {"ok": True, "released": self.lease_manager.release_lease(lease_id)}

    def warm(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        model = payload.get("model") or self.default_model
        keep_alive = payload.get("keep_alive") or "30m"
        prompt = payload.get("prompt") or "ping"
        started = time.perf_counter()
        data = self.client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.0, "num_predict": 1},
            keep_alive=keep_alive,
            timeout=int(payload.get("timeout") or self.timeout),
        )
        return {
            "ok": True,
            "model": model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "response": data.get("message", {}).get("content"),
        }

    def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = payload.get("model") or self.default_model
        started = time.perf_counter()
        data = self.client.chat(
            model=model,
            messages=payload.get("messages") or [],
            format=payload.get("format"),
            options=payload.get("options"),
            keep_alive=payload.get("keep_alive"),
            timeout=int(payload.get("timeout") or self.timeout),
        )
        return {
            "ok": True,
            "model": model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "message": data.get("message", {}),
            "raw": data,
        }

    def judge(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = payload.get("model") or self.default_model
        prompt = build_judge_prompt(payload)
        started = time.perf_counter()
        data = self.client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0.1},
            keep_alive=payload.get("keep_alive"),
            timeout=int(payload.get("timeout") or self.timeout),
        )
        content = data.get("message", {}).get("content", "{}")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {
                "is_high_quality": False,
                "failure_reason": "judge_json_parse_error",
                "score": 0.0,
            }
        return {
            "ok": True,
            "model": model,
            "latency_ms": int((time.perf_counter() - started) * 1000),
            "result": parsed,
            "raw_content": content,
        }

    def unload(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        stopped = self.client.unload(payload.get("model"))
        return {"ok": True, "stopped_models": stopped}


def build_judge_prompt(payload: dict[str, Any]) -> str:
    context = payload.get("context") or "No context provided."
    if isinstance(context, list):
        context = "\n\n".join(str(item) for item in context)
    rubric = payload.get("rubric") or DEFAULT_JUDGE_RUBRIC
    return rubric.format(
        context=context,
        input=payload.get("input", ""),
        actual_output=payload.get("actual_output") or payload.get("output", ""),
    )


def make_handler(service: InferenceService) -> type[BaseHTTPRequestHandler]:
    class InferenceRequestHandler(BaseHTTPRequestHandler):
        server_version = "UCoreInferenceServer/0.1"

        def log_message(
            self, format: str, *args: Any
        ) -> None:  # pragma: no cover - keep tests/logs quiet
            return None

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/health":
                self._write_json(200, {"ok": True})
            elif self.path == "/status":
                self._handle(lambda: service.status())
            else:
                self._write_json(404, {"ok": False, "error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            payload = self._read_json()
            if self.path == "/warm":
                self._handle(lambda: service.warm(payload))
            elif self.path == "/chat":
                self._handle(lambda: service.chat(payload))
            elif self.path == "/judge":
                self._handle(lambda: service.judge(payload))
            elif self.path == "/unload":
                self._handle(lambda: service.unload(payload))
            elif self.path == "/lease":
                self._handle(lambda: service.lease(payload))
            elif self.path == "/release":
                self._handle(lambda: service.release(payload))
            else:
                self._write_json(404, {"ok": False, "error": "not_found"})

        def _handle(self, fn: Callable[[], dict[str, Any]]) -> None:
            try:
                self._write_json(200, fn())
            except Exception as exc:
                self._write_json(500, {"ok": False, "error": str(exc)})

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw else {}

        def _write_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return InferenceRequestHandler


def serve(config: InferenceServerConfig) -> None:
    client = OllamaHTTPClient(config.ollama_host, timeout=config.timeout)
    service = InferenceService(
        client=client, default_model=config.default_model, timeout=config.timeout
    )
    server = ThreadingHTTPServer((config.host, config.port), make_handler(service))
    print(
        json.dumps(
            {
                "ok": True,
                "event": "inference_server_started",
                "host": config.host,
                "port": config.port,
                "ollama_host": config.ollama_host,
                "default_model": service.default_model,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server.serve_forever()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local ucore inference control server")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
        p.add_argument("--model", default=None)
        p.add_argument("--timeout", type=int, default=180)

    serve_p = sub.add_parser("serve", help="Run HTTP server with /status /warm /judge /unload")
    serve_p.add_argument("--host", default=DEFAULT_HOST)
    serve_p.add_argument("--port", type=int, default=DEFAULT_PORT)
    add_common(serve_p)

    status_p = sub.add_parser("status", help="Print backend/model status as JSON")
    add_common(status_p)

    warm_p = sub.add_parser("warm", help="Warm selected model with a tiny chat call")
    add_common(warm_p)
    warm_p.add_argument("--keep-alive", default="30m")
    warm_p.add_argument("--prompt", default="ping")

    judge_p = sub.add_parser("judge", help="Run one JSON judge call")
    add_common(judge_p)
    judge_p.add_argument("--input", required=True)
    judge_p.add_argument("--actual-output", required=True)
    judge_p.add_argument("--context", action="append", default=[])

    lease_p = sub.add_parser("lease", help="Acquire GPU lease for exclusive training access")
    add_common(lease_p)
    lease_p.add_argument(
        "--mode",
        default="judge_shared",
        choices=["judge_shared", "generation_shared", "train_exclusive"],
    )
    lease_p.add_argument("--ttl", type=int, default=300, help="Lease TTL in seconds")

    release_p = sub.add_parser("release", help="Release a GPU lease by ID")
    add_common(release_p)
    release_p.add_argument("--lease-id", required=True, help="Lease ID to release")

    unload_p = sub.add_parser("unload", help="Unload one model or all running Ollama models")
    add_common(unload_p)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if args.command == "serve":
        serve(
            InferenceServerConfig(
                host=args.host,
                port=args.port,
                ollama_host=args.ollama_host,
                default_model=args.model,
                timeout=args.timeout,
            )
        )
        return 0

    client = OllamaHTTPClient(args.ollama_host, timeout=args.timeout)
    service = InferenceService(client=client, default_model=args.model, timeout=args.timeout)
    if args.command == "status":
        _print_json(service.status())
    elif args.command == "warm":
        _print_json(
            service.warm(
                {"model": args.model, "keep_alive": args.keep_alive, "prompt": args.prompt}
            )
        )
    elif args.command == "judge":
        _print_json(
            service.judge(
                {
                    "model": args.model,
                    "input": args.input,
                    "actual_output": args.actual_output,
                    "context": args.context,
                }
            )
        )
    elif args.command == "unload":
        _print_json(service.unload({"model": args.model}))
    elif args.command == "lease":
        _print_json(service.lease({"mode": args.mode, "ttl": args.ttl}))
    elif args.command == "release":
        _print_json(service.release({"lease_id": args.lease_id}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
