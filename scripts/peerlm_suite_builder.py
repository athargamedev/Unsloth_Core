#!/usr/bin/env python3
"""
PeerLM suite builder via REST API.
Bypasses MCP serialization issues by directly calling PeerLM endpoints.
"""

import json
import os
import sys
from typing import Optional
import requests


class PeerLMClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("PEERLM_API_KEY")
        if not self.api_key:
            raise ValueError("PEERLM_API_KEY not set")
        self.base_url = "https://api.peerlm.com/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def create_system_prompt(self, name: str, system_prompt: str, description: str = "", tags: Optional[list] = None) -> str:
        """Create a system prompt and return its ID."""
        payload = {
            "name": name,
            "system_prompt": system_prompt,
            "description": description,
            "tags": tags or []
        }
        resp = self.session.post(f"{self.base_url}/system-prompts", json=payload)
        resp.raise_for_status()
        return resp.json()["id"]

    def create_test_prompt(self, title: str, prompt: str, description: str = "", tags: Optional[list] = None) -> str:
        """Create a test prompt and return its ID."""
        payload = {
            "title": title,
            "prompt": prompt,
            "description": description,
            "tags": tags or []
        }
        resp = self.session.post(f"{self.base_url}/test-prompts", json=payload)
        resp.raise_for_status()
        return resp.json()["id"]

    def create_suite(
        self,
        name: str,
        description: str,
        generator_models: list,
        evaluator_models: list,
        system_prompt_ids: list,
        test_prompt_ids: list,
        criteria: list,
        deterministic_mode: bool = True,
        evaluation_method: str = "rubric",
        samples_per_prompt: int = 1
    ) -> str:
        """Create an evaluation suite and return its ID."""
        payload = {
            "name": name,
            "description": description,
            "generator_models": generator_models,
            "evaluator_models": evaluator_models,
            "system_prompt_ids": system_prompt_ids,
            "test_prompt_ids": test_prompt_ids,
            "criteria": criteria,
            "deterministic_mode": deterministic_mode,
            "evaluation_method": evaluation_method,
            "samples_per_prompt": samples_per_prompt
        }
        resp = self.session.post(f"{self.base_url}/suites", json=payload)
        resp.raise_for_status()
        return resp.json()["id"]

    def run_suite(self, suite_id: str) -> str:
        """Trigger a suite run and return the run ID."""
        resp = self.session.post(f"{self.base_url}/suites/{suite_id}/run", json={})
        resp.raise_for_status()
        return resp.json()["run_id"]

    def get_run_results(self, run_id: str) -> dict:
        """Fetch run results."""
        resp = self.session.get(f"{self.base_url}/runs/{run_id}")
        resp.raise_for_status()
        return resp.json()


def main():
    client = PeerLMClient()

    # Step 1: Create system prompt
    print("Creating system prompt...")
    system_prompt_id = client.create_system_prompt(
        name="NPC Knowledge Evaluator",
        system_prompt="""You are an expert evaluator assessing how well an NPC (non-player character) has learned domain-specific knowledge during fine-tuning. Rate each response on Factual Accuracy, Completeness, Clarity, and Persona Adherence on a 1-5 scale.""",
        description="Evaluator persona for assessing NPC LoRA fine-tuning quality",
        tags=["npc-evaluation"]
    )
    print(f"✓ System prompt ID: {system_prompt_id}")

    # Step 2: Create test prompts
    test_prompts = [
        {
            "title": "Chemistry: Balancing Chemical Equations",
            "prompt": "Explain how to balance the chemical equation: C + O₂ → CO₂. Walk through the step-by-step process.",
            "description": "Tests stoichiometry understanding",
            "tags": ["chemistry", "stoichiometry"]
        },
        {
            "title": "Chemistry: Acid-Base Reactions",
            "prompt": "What happens when hydrochloric acid reacts with sodium hydroxide?",
            "description": "Tests acid-base chemistry knowledge",
            "tags": ["chemistry", "acid-base"]
        },
        {
            "title": "Biology: Photosynthesis",
            "prompt": "Describe the two main stages of photosynthesis and their key inputs/outputs.",
            "description": "Tests photosynthesis understanding",
            "tags": ["biology", "photosynthesis"]
        },
        {
            "title": "Biology: Cellular Respiration",
            "prompt": "How does cellular respiration break down glucose? Compare aerobic and anaerobic respiration.",
            "description": "Tests respiration knowledge",
            "tags": ["biology", "respiration"]
        },
        {
            "title": "Identity & Voice: NPC Persona",
            "prompt": "What is your background and teaching approach? Who are you?",
            "description": "Tests persona consistency",
            "tags": ["identity", "persona"]
        }
    ]

    test_prompt_ids = []
    print("\nCreating test prompts...")
    for tp in test_prompts:
        tid = client.create_test_prompt(
            title=tp["title"],
            prompt=tp["prompt"],
            description=tp["description"],
            tags=tp["tags"]
        )
        test_prompt_ids.append(tid)
        print(f"✓ {tp['title']}: {tid}")

    # Step 3: Create suite
    print("\nCreating evaluation suite...")
    suite_id = client.create_suite(
        name="NPC Fine-Tune Evaluation Suite",
        description="Blind comparison of NPC LoRA adapters trained via template/Ollama dataset generation",
        generator_models=["anthropic/claude-haiku-4.5", "anthropic/claude-opus-4.1"],
        evaluator_models=["google/gemini-2.5-flash"],
        system_prompt_ids=[system_prompt_id],
        test_prompt_ids=test_prompt_ids,
        criteria=[
            {"label": "Factual Accuracy", "description": "Scientific correctness", "weight": 4},
            {"label": "Completeness", "description": "Coverage of key concepts", "weight": 3},
            {"label": "Clarity", "description": "Understandability", "weight": 2},
            {"label": "Persona Adherence", "description": "Reflects NPC character", "weight": 3}
        ],
        deterministic_mode=True,
        evaluation_method="rubric",
        samples_per_prompt=1
    )
    print(f"✓ Suite created: {suite_id}")

    # Step 4: Save result
    result = {
        "system_prompt_id": system_prompt_id,
        "test_prompt_ids": test_prompt_ids,
        "suite_id": suite_id
    }

    output_file = "/tmp/peerlm_suite_result.json"
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✓ Results saved to {output_file}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
