#!/usr/bin/env python3
"""
Prototype: GRPO (Generative Reward Process Optimization) Training with DeepEval.
This script demonstrates how to train a small 3B model using DeepEval metrics as the reward function.
Instead of static SFT, the model learns to maximize the Confident AI Persona Fit score.
"""

import os
import sys
import torch
from pathlib import Path
from datasets import load_dataset, Dataset

try:
    from unsloth import FastLanguageModel, PatchDPOTrainer
    PatchDPOTrainer() # Unsloth optimizes RLHF/DPO/GRPO trainers
    from trl import GRPOTrainer, GRPOConfig
except ImportError:
    print("Unsloth or TRL not installed with GRPO support.")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# --- DeepEval Reward Function ---
# In GRPO, the reward function takes a list of prompts and corresponding completions.
# It returns a list of floats (the rewards).

def deepeval_persona_reward(prompts: list[str], completions: list[list[dict]], **kwargs) -> list[float]:
    """
    Reward function that uses DeepEval's LLM-as-a-judge to score the completion.
    This simulates RLHF without human labelers.
    """
    # Import inside to avoid slow startup if just viewing help
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCase, SingleTurnParams
    from tests.evals.metrics import JUDGE_MODEL
    import asyncio
    
    # We use a custom lightweight GEval to score the model's output
    metric = GEval(
        name="GRPO Persona Reward",
        criteria="Score whether the response is exactly 3-5 sentences, uses cause and effect, and avoids markdown.",
        evaluation_params=[SingleTurnParams.INPUT, SingleTurnParams.ACTUAL_OUTPUT],
        model=JUDGE_MODEL,
        threshold=0.5,
    )
    
    rewards = []
    
    # GRPOTrainer passes completions as a list of message lists (if format is conversational)
    # We extract the last assistant message content.
    for prompt, completion_msgs in zip(prompts, completions):
        try:
            # completion_msgs is usually [{'role': 'assistant', 'content': '...'}]
            # We extract the actual string output
            output_text = completion_msgs[-1]["content"] if isinstance(completion_msgs, list) else completion_msgs
            
            test_case = LLMTestCase(
                input=prompt,
                actual_output=output_text,
            )
            
            # DeepEval is async by default, we can run sync here for the reward pipeline
            # Note: For production, batching API calls is highly recommended.
            metric.measure(test_case)
            
            # Use the score as the reward (0.0 to 1.0)
            rewards.append(float(metric.score))
        except Exception as e:
            print(f"Reward scoring failed: {e}")
            rewards.append(0.0) # 0 reward on failure
            
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
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )
    
    # Create a dummy dataset for the prototype
    # In practice, this would load train_clean.jsonl but only keep the prompts.
    dataset = Dataset.from_dict({
        "prompt": [
            "Explain the fall of Rome.",
            "What was the impact of the printing press?",
            "Tell me about Ancient Egypt."
        ]
    })
    
    training_args = GRPOConfig(
        output_dir="outputs/grpo_deepeval",
        learning_rate=5e-6,
        per_device_train_batch_size=1, # Small batch for 6GB VRAM
        gradient_accumulation_steps=4,
        max_steps=10, # Just a prototype run
        optim="adamw_8bit",
        logging_steps=1,
        bf16=torch.cuda.is_bf16_supported(),
        fp16=not torch.cuda.is_bf16_supported(),
        # GRPO specific:
        num_generations=2, # Number of completions to generate per prompt for reward comparison
        max_prompt_length=256,
        max_completion_length=256,
    )
    
    trainer = GRPOTrainer(
        model=model,
        reward_funcs=[deepeval_persona_reward],
        args=training_args,
        train_dataset=dataset,
    )
    
    print("\nStarting GRPO Training loop (Prototype)...")
    print("The model will generate 2 completions per prompt, score them using DeepEval (Ollama),")
    print("and use the difference to update the LoRA weights.")
    # trainer.train() # Commented out so it doesn't run and consume VRAM in this mock environment

if __name__ == "__main__":
    main()
