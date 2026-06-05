#!/usr/bin/env python3
"""
Prototype: GRPO (Generative Reward Process Optimization) Training with DeepEval.
This script demonstrates how to train a small 3B model using DeepEval metrics as the reward function.
Instead of static SFT, the model learns to maximize the Confident AI Persona Fit score.
"""

import sys
from pathlib import Path

import torch
from datasets import Dataset

try:
    from unsloth import FastLanguageModel, PatchDPOTrainer

    PatchDPOTrainer()  # Unsloth optimizes RLHF/DPO/GRPO trainers
    from trl import GRPOConfig, GRPOTrainer
except ImportError:
    print("Unsloth or TRL not installed with GRPO support.")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- DeepEval Reward Function ---


def deepeval_persona_reward(
    prompts: list[str], completions: list[list[dict]], **kwargs
) -> list[float]:
    """
    Reward function that uses DeepEval's LLM-as-a-judge to score the completion.
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams
    from tests.evals.metrics import JUDGE_MODEL

    # Use the same rubric as dataset evaluation for consistency
    metric = GEval(
        name="GRPO Persona Reward",
        criteria=(
            "Score whether the response matches the NPC persona: expert, short (1-3 sentences), "
            "never mentions being an AI, and strictly avoids markdown (##, **, lists)."
        ),
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=JUDGE_MODEL,
        threshold=0.7,
    )

    rewards = []
    for prompt, completion_msgs in zip(prompts, completions, strict=False):
        try:
            output_text = (
                completion_msgs[-1]["content"]
                if isinstance(completion_msgs, list)
                else completion_msgs
            )
            test_case = LLMTestCase(input=prompt, actual_output=output_text)
            metric.measure(test_case)
            rewards.append(float(metric.score))
        except Exception as e:
            print(f"Reward scoring failed: {e}")
            rewards.append(0.0)

    return rewards


def sentence_length_reward(
    prompts: list[str], completions: list[list[dict]], **kwargs
) -> list[float]:
    """Reward for keeping responses between 1 and 3 sentences."""
    import re

    rewards = []
    for completion_msgs in completions:
        text = (
            completion_msgs[-1]["content"] if isinstance(completion_msgs, list) else completion_msgs
        )
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        count = len(sentences)
        if 1 <= count <= 3:
            rewards.append(1.0)
        elif count == 0:
            rewards.append(0.0)
        else:
            # Linear penalty for being too long
            rewards.append(max(0.0, 1.0 - (count - 3) * 0.2))
    return rewards


def no_markdown_reward(prompts: list[str], completions: list[list[dict]], **kwargs) -> list[float]:
    """Penalty for using forbidden markdown (bold, headers, lists)."""
    forbidden = [r"\*\*", r"###", r"##", r"^- ", r"^\d\. "]
    import re

    rewards = []
    for completion_msgs in completions:
        text = (
            completion_msgs[-1]["content"] if isinstance(completion_msgs, list) else completion_msgs
        )
        penalty = 0.0
        for pattern in forbidden:
            if re.search(pattern, text, re.MULTILINE):
                penalty += 0.5
        rewards.append(max(0.0, 1.0 - penalty))
    return rewards


def main():
    print("Initializing Unsloth GRPO Training with DeepEval Rewards...")

    model_name = "unsloth/Llama-3.2-3B-Instruct"
    max_seq_length = 2048

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # Create a dummy dataset for the prototype
    # In practice, this would load train_clean.jsonl but only keep the prompts.
    dataset = Dataset.from_dict(
        {
            "prompt": [
                "Explain the fall of Rome.",
                "What was the impact of the printing press?",
                "Tell me about Ancient Egypt.",
            ]
        }
    )

    training_args = GRPOConfig(
        output_dir="outputs/grpo_deepeval",
        learning_rate=5e-6,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        max_steps=10,
        optim="adamw_8bit",
        logging_steps=1,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        # GRPO specific:
        num_generations=2,  # Required min 2
        max_prompt_length=32,  # Even more reduced
        max_completion_length=32,  # Even more reduced
    )

    trainer = GRPOTrainer(
        model=model,
        reward_funcs=[
            deepeval_persona_reward,
            sentence_length_reward,
            no_markdown_reward,
        ],
        args=training_args,
        train_dataset=dataset,
    )

    print("\nStarting GRPO Training loop (Prototype)...")
    print("The model will generate 2 completions per prompt, score them using DeepEval (Ollama),")
    print("and use the difference to update the LoRA weights.")
    trainer.train()


if __name__ == "__main__":
    main()
