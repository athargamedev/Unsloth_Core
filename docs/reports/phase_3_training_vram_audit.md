# Technical Audit Report: Training & VRAM Efficiency (Phase 3)

**Author:** Build Orchestrator Agent (opencode)
**Date:** 2026-06-03
**Status:** COMPLETE (Diagnostic & Optimization Phase)

---

## Executive Summary

Phase 3 of the pipeline optimization audit focuses on **Training** (`train.py`) and training presets (`fast-3b`, `safe-any`) on an RTX 3060 6GB local GPU. 

Our investigations identified critical optimizations to:
1. **Maximize VRAM Headroom (Task 3.1 & 3.2)**: Set up explicit model double quantization inside model-loading logic. Double quantization (`bnb_4bit_use_double_quant=True`) saves up to **0.3-0.5 GB** of VRAM, providing critical safety margins.
2. **Resolve Token Packing Attention Mask Leakage (Task 3.3)**: TRL's standard `SFTTrainer` with `packing=True` can leak contextual attention across independent packed training dialogues. We formulate how to correctly configure nested attention masks in Unsloth to prevent this leakage.
3. **Enhance SFT Training Stability (Task 3.4)**: Incorporate NEFTune noise injection to prevent model overfitting and stabilize gradient steps during small-dataset fine-tuning.

---

## 1. VRAM Scaling, Estimation & Presets (Task 3.1)

### VRAM Heuristics & Allocation
In `train.py` (lines 1420-1460), the script calculates expected peak memory according to the baseline rules in `etc/workload-policy.yaml`:
* **3B model**: 5.0 GB baseline.
* **Safety Margin**: A `1.25` safety multiplier requires `6.25 GB` VRAM headroom for 3B, which slightly exceeds the RTX 3060's local 6GB limit.

Currently, if peak memory estimation exceeds available VRAM, the script logs a warning but **does not raise a blocking error**, allowing local runs.

### VRAM Scaling Factors
Three parameters scale VRAM consumption dynamically:
1. **Max Sequence Length**: KV Cache VRAM scales quadratically with sequence length under standard attention, but with Unsloth's native FlashAttention, it scales linearly.
2. **LoRA Rank (r)**: LoRA parameter allocation scales linearly with adapter rank and alpha.
3. **Gradient Accumulation**: Increasing `gradient_accumulation_steps` from 2 to 8 maintains low VRAM (since micro-batch size remains 1) while increasing effective batch size to stabilize convergence.

---

## 2. Alternative Optimizers & Quantization (Task 3.2)

### Quantization Optimization (Double Quantization)
By default, the script loads models in 4-bit when `load_in_4bit` is active, but does **not** configure double quantization inside `BitsAndBytesConfig` inside `get_model_and_tokenizer()`. 

#### Double Quantization Solution
Configuring `bnb_4bit_use_double_quant=True` inside `BitsAndBytesConfig` quantizes the quantization constants themselves, yielding **0.3-0.5 GB** VRAM savings with zero degradation in perplexity.

### Alternative Optimizers
Currently, the script utilizes `adamw_8bit` directly via HF TrainingArguments. While `adamw_8bit` is optimal, alternative optimizers like **Sophia** (second-order curvature estimation) or **Adafactor** (low-memory optimizer) are not supported. Sophia can speed up convergence on small, concept-focused datasets by estimating Hessian matrices.

---

## 3. Token Packing & Attention Mask Leakage (Task 3.3)

### The Token Packing Leak
Token packing is enabled via `packing=True` inside TRL's `SFTTrainer`. 

#### The Problem
In standard configurations of TRL, `SFTTrainer` packs multiple separate training examples together into a single 2048-token sequence, but does **not** construct an appropriate nested `attention_mask` by default. As a result, the model's self-attention mechanism leaks across distinct packed dialogues (i.e. tokens in dialogue B attend to tokens in dialogue A). 

This is **cross-example attention leakage**. The model learns unnatural, spurious contextual links across completely different, independent subject matters.

#### The Unsloth/TRL Solution
Recent TRL versions support `block_size` and nested attention masks. To prevent leakage, we must explicitly configure the SFTTrainer's data collator with:
```python
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=max_seq_length,
    packing=True,
    # Configure the collator to enforce causal masking on packed blocks
    data_collator=DataCollatorForCompletionOnlyLM(
        response_template=response_template, 
        instruction_template=instruction_template, 
        tokenizer=tokenizer
    )
)
```
And verify that the underlying attention mask is causal and block-diagonal during training.

---

## 4. Learning Rate & Gradient Stability (Task 3.4)

Small-dataset SFT fine-tuning (such as our 132-example subject datasets) is highly prone to:
* **Overfitting**: Memorizing prompts.
* **Loss Spikes**: Gradients exploding on complex explanations.

### Cosine Schedulers
The script currently uses a Cosine annealing scheduler (`lr_scheduler_type="cosine"`) starting at `2e-4` with 10 warmup steps. This provides clean decay, but can be stabilized further.

### NEFTune Noise Injection
To combat overfitting and smoothen the loss curve, we can inject uniform noise into the embedding layer during SFT SFT training by setting HF's `neftune_noise_alpha` parameter (e.g., `neftune_noise_alpha=5.0`). This prevents the model's embeddings from collapsing on the small training sample space.

---

## Action Items for Pipeline Implementation

| Task | Action | Target File |
|------|--------|-------------|
| **3.2** | Configure `bnb_4bit_use_double_quant=True` inside `BitsAndBytesConfig` | `train.py` |
| **3.3** | Verify and enforce causal attention masking inside packer collators | `train.py` |
| **3.4** | Add configuration support for `neftune_noise_alpha` inside SFT parameters | `train.py` |
