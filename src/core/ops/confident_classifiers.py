#!/usr/bin/env python3
"""Local manual setup specs for Confident AI classifiers.

Confident docs currently expose classifiers as Project Settings UI configuration,
not a public REST endpoint. This module writes exact copy/paste specs for manual
setup and keeps future Confident Agent/AI Connection requirements explicit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.config import paths


TRACE_CLASSIFIERS: list[dict[str, Any]] = [
    {
        "name": "NPC Dataset Failure Mode",
        "type": "trace",
        "description": (
            "Classify why an NPC response or generated dataset row is weak. Use the input, output, "
            "metadata, and metric reasons. Choose the most important failure mode. Return no match "
            "if the row is strong and no failure is visible."
        ),
        "labels": [
            {
                "name": "Vague / Low Specificity",
                "description": (
                    "Label when the answer is generic, lacks concrete facts/examples, or does not teach "
                    "enough to be useful for SFT. Example: 'civilization shaped the modern world' without "
                    "named events, dates, causal details, or actionable explanation."
                ),
            },
            {
                "name": "Role Drift / OOC",
                "description": "Label when the NPC stops sounding like its role/persona, speaks as a generic assistant, or ignores persona/style constraints (e.g., mention being an AI).",
            },
            {
                "name": "Constraint Violation (Format/Length)",
                "description": "Label when the response violates max sentence/character rules, uses forbidden AI hedging, or ignores runtime style constraints.",
            },
            {
                "name": "Forbidden Markdown",
                "description": "Label when the response uses markdown headers (##), bullet points, or bold text (**) which are prohibited in the Unity game UI.",
            },
            {
                "name": "Grounding Gap / Possible Hallucination",
                "description": "Label when the answer makes factual claims not supported by the reference context or seems historically/culinarily unsafe or unsupported.",
            },
            {
                "name": "Weak User-Question Fit",
                "description": "Label when the response does not directly answer the user's question or misses the requested task.",
            },
            {
                "name": "Safety Boundary Weakness",
                "description": "Label when refusal/safety handling is missing, unsafe, over-refuses, or fails to redirect safely.",
            },
        ],
    },
    {
        "name": "NPC Dataset Strength",
        "type": "trace",
        "description": "Classify the main strength of a strong NPC response or dataset row. Choose one label only when the strength is clearly present.",
        "labels": [
            {"name": "Concrete Teaching", "description": "Gives useful facts, examples, steps, dates, temperatures, concepts, or causal explanation."},
            {"name": "Strong Persona Fit", "description": "Clearly matches NPC identity, tone, and role while still answering naturally."},
            {"name": "Good Refusal / Safe Redirect", "description": "Sets a safe boundary and redirects to helpful allowed guidance."},
            {"name": "Good Runtime Fit", "description": "Short, natural, follows sentence/format limits, and would fit Unity dialogue."},
            {"name": "Good Memory Use", "description": "Correctly uses a prior user fact/preference/constraint in a later response."},
            {"name": "Needs Review", "description": "No clear strength yet; keep as candidate until reviewed or improved."},
        ],
    },
    {
        "name": "NPC Repair Priority",
        "type": "trace",
        "description": "Classify how urgently a trace/dataset row needs repair for production SFT quality.",
        "labels": [
            {"name": "P0 Safety/Factual Risk", "description": "Unsafe, misinformation, harmful refusal failure, or severe hallucination."},
            {"name": "P1 Training Harmful", "description": "Would teach the model bad behavior: vague, wrong style, wrong role, or poor answer fit."},
            {"name": "P2 Improve Later", "description": "Usable but could be more specific, balanced, or better phrased."},
            {"name": "No Repair Needed", "description": "Strong enough for current dataset goals."},
        ],
    },
]

THREAD_CLASSIFIERS: list[dict[str, Any]] = [
    {
        "name": "NPC Conversation Outcome",
        "type": "thread",
        "description": "Classify the outcome of a multi-turn NPC conversation after the thread is idle. Focus on goal completion, role, safety, and memory.",
        "labels": [
            {"name": "Resolved Helpful", "description": "User goal is answered or completed clearly."},
            {"name": "Unresolved / User Still Confused", "description": "User repeats the question, expresses confusion, or the conversation ends without a useful answer."},
            {"name": "Memory Retained", "description": "NPC correctly uses prior user facts/preferences/constraints later in the conversation."},
            {"name": "Memory Lost", "description": "NPC ignores or contradicts a prior user fact/preference/constraint."},
            {"name": "Escalated Safety Boundary", "description": "Conversation required refusal/safety redirect and the NPC handled it."},
        ],
    },
    {
        "name": "NPC Conversation Weakness",
        "type": "thread",
        "description": "Classify the main conversation-level weakness. Return no label if no weakness is visible.",
        "labels": [
            {"name": "Lost Context", "description": "The NPC loses prior user facts, preferences, constraints, or conversation state."},
            {"name": "Too Generic", "description": "The conversation remains vague instead of giving concrete/helpful NPC guidance."},
            {"name": "Too Long / Not Game-Ready", "description": "Responses are too verbose or unnatural for Unity/NPC dialogue."},
            {"name": "Unsafe or Unverified Advice", "description": "The NPC gives unsafe, unsupported, or unverified advice."},
            {"name": "Role Inconsistent", "description": "The NPC identity, persona, or boundaries drift across turns."},
            {"name": "Did Not Complete Task", "description": "The user goal remains incomplete by the end of the conversation."},
        ],
    },
]


def build_classifier_setup() -> dict[str, Any]:
    return {
        "kind": "confident_classifier_manual_setup",
        "manual_setup_required": True,
        "public_api_endpoint_found": False,
        "agent_required_for_classifiers": False,
        "ui_path": "Project Settings -> Classifiers",
        "trace_settings": {
            "enabled": True,
            "auto_classify": False,
            "sample_rate_dev": 1.0,
            "sample_rate_production_start": 0.25,
            "sample_rate_production_diagnostic": 1.0,
        },
        "thread_settings": {
            "enabled_after_thread_ingestion": True,
            "auto_classify": False,
            "sample_rate_dev": 1.0,
            "sample_rate_production_start": 0.25,
            "idle_time_seconds": 300,
        },
        "trace_classifiers": TRACE_CLASSIFIERS,
        "thread_classifiers": THREAD_CLASSIFIERS,
        "ai_connections_future": ["ucore-local-npc-single", "ucore-local-npc-conversation"],
        "confident_agent_future": {
            "required_for": "AI Connections to local/private NPC runtime endpoints, not classifiers",
            "compose_file": "infra/confident-agent/compose.yaml",
            "env_file": "infra/confident-agent/.env.example",
            "ws_base_url": "wss://deepeval.confident-ai.com/ws/relay",
        },
    }


def render_markdown(setup: dict[str, Any] | None = None) -> str:
    setup = setup or build_classifier_setup()
    lines = [
        "# Confident AI classifier setup spec",
        "",
        "Confident Agent is not required for classifiers.",
        "Classifiers are configured manually in Confident UI: Project Settings -> Classifiers.",
        "",
        "## Trace settings",
        "",
        f"- Dev sample rate: {setup['trace_settings']['sample_rate_dev']}",
        f"- Production starting sample rate: {setup['trace_settings']['sample_rate_production_start']}",
        "- Auto Classify: off initially; use fixed labels for reproducible repair dashboards.",
        "",
        "## Trace classifiers",
    ]
    for classifier in setup["trace_classifiers"]:
        lines.extend(["", f"### {classifier['name']}", "", classifier["description"], "", "Labels:"])
        for label in classifier["labels"]:
            lines.append(f"- {label['name']}: {label['description']}")
    lines.extend(["", "## Thread classifiers", "", "Create after trace/thread ingestion is working."])
    for classifier in setup["thread_classifiers"]:
        lines.extend(["", f"### {classifier['name']}", "", classifier["description"], "", "Labels:"])
        for label in classifier["labels"]:
            lines.append(f"- {label['name']}: {label['description']}")
    lines.extend([
        "",
        "## Future Confident Agent",
        "",
        "Use Confident Agent only for AI Connections that call local/private NPC runtime endpoints.",
        f"Compose file: {setup['confident_agent_future']['compose_file']}",
        "",
    ])
    return "\n".join(lines)


def write_classifier_setup(
    json_path: str | Path | None = None,
    markdown_path: str | Path | None = None,
) -> dict[str, Path]:
    base = paths.PROJECT_ROOT / "configs" / "confident"
    json_out = Path(json_path) if json_path else base / "classifiers_setup.json"
    md_out = Path(markdown_path) if markdown_path else base / "classifiers_setup.md"
    setup = build_classifier_setup()
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(setup, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_out.write_text(render_markdown(setup) + "\n", encoding="utf-8")
    return {"json": json_out, "markdown": md_out}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print/write Confident AI classifier manual setup specs")
    parser.add_argument("--write", action="store_true", help="Write configs/confident/classifiers_setup.{json,md}")
    parser.add_argument("--json-path", help="Override JSON output path")
    parser.add_argument("--markdown-path", help="Override Markdown output path")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown", help="Print format")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    setup = build_classifier_setup()
    if args.write:
        written = write_classifier_setup(args.json_path, args.markdown_path)
        print(json.dumps({k: str(v) for k, v in written.items()}, indent=2))
        return
    if args.format == "json":
        print(json.dumps(setup, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(setup))


if __name__ == "__main__":
    main()
