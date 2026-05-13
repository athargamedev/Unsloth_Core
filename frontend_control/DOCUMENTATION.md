# UNITY NPC CORE: Technical Documentation

## 1. Project Overview
**Unity NPC Core** is a high-performance orchestration dashboard designed for fine-tuning Large Language Models (LLMs) specifically for non-player character (NPC) dialogue systems. It bridges the gap between raw training data and integrated game assets by providing a visual management layer for the LoRA (Low-Rank Adaptation) training workflow.

---

## 2. Core Architecture & Nuances

### 2.1 The Training Pipeline
The system conceptualizes training as a four-stage deterministic workflow:
1.  **Dataset Prep**: Validating and deduplicating dialogue pairs.
2.  **Hyperparam Tuning**: Determining the optimal Rank (R) and Alpha for the specific character personality.
3.  **Training**: The main execution loop where the adapter weights are learned.
4.  **Evaluation**: Calculating BLEU/Perplexity scores against a validation set.

### 2.2 Dataset Versioning Strategy
Unlike standard file storage, this project implements a **Versioned Asset Factory**. 
-   **Nuance**: Every modification to a dataset is tagged (e.g., `v1.0.0`, `v1.1.0`).
-   **Benefit**: This allows "time-travel" debugging where a developer can revert to a dataset version that yielded higher semantic coverage if a newer version causes "mode collapse" or repetitive greeting patterns.

### 2.3 Real-time Monitoring & Analytics (TensorBoard Lite)
The **TensorBoard** view provides granular scalar tracking:
-   **Loss Smoothing**: The charts utilize a 0.6 smoothing factor to highlight long-term convergence trends over short-term noise.
-   **Resource Context**: The system displays VRAM usage alongside training metrics to prevent "Out of Memory" (OOM) errors during high-rank training sessions.

### 2.4 Model Comparison View
A dedicated side-by-side view allows users to compare different training runs.
-   **Nuance**: It focuses on the relationship between hyperparameters and results. For example, comparing how a Rank of 16 vs 32 affects final loss in relation to VRAM consumption.

---

## 3. Navigation & Interface Logic

-   **Operations Matrix**: The "Control Center" for all active background processes.
-   **System Hub**: A direct bridge to the underlying infrastructure (mocked), providing emergency kills for zombie PIDs and cache management.
-   **AI Assistant**: A specialized sidebar trained on Unity LLM best practices, offering contextual tips like "Adjust temperature to 0.4 for Bard datasets."

---

## 4. Future Improvements & Roadmap

### 4.1 Phase 1: Real Compute Integration
-   **External Provider Bridges**: Connect to APIs like RunPod, LambdaLabs, or Modal to launch actual GPU clusters.
-   **Local CUDA support**: Enable direct interaction with local NVIDIA drivers via a Python wrapper.

### 4.2 Phase 2: Advanced Data Synthesis
-   **Agentic Dataset Generation**: Use Gemini 1.5 Pro to automatically generate character backstories and dialogue samples based on 3-5 seed sentences.
-   **Conflict Simulation**: A feature to "play-test" the NPC in the browser before exporting, allowing developers to chat with the newly trained model in a sandbox.

### 4.3 Phase 3: Unity Runtime Bridge
-   **One-Click Deployment**: A C# SDK for Unity that fetches trained adapters directly from this dashboard's API.
-   **Hot-swapping**: Change NPC personalities in a running game instance via the dashboard for rapid iteration.

### 4.4 Phase 4: Collaborative Ecosystem
-   **Shared Hub**: A library of community-trained character adapters (e.g., "Standard Tavern Keeper", "Aggressive Guard").
-   **Multi-User Workspaces**: Allowing teams of narrative designers to collaborate on the same character's dialogue evolution.

---

## 5. Security & Safety
-   **PII Scrubbing**: Future releases will include an automatic PII (Personally Identifiable Information) scrubber for datasets to comply with privacy regulations.
-   **Sanity Checks**: Automated validation to ensure hyperparameter combinations (like extremely high LR) don't waste expensive GPU hours on obviously failing runs.
