# LLMUnity Integration Guide

## Overview

LLMUnity uses a **dual-GGUF strategy**:
- **Single shared base model** (e.g., `llama-3.2-3b-instruct-q4_k_m.gguf`) loaded once at startup.
- **Multiple LoRA adapters** (e.g., `<npc>-lora-f16.gguf`) registered and switched at runtime.

The base model never changes; only LoRA weights are swapped when switching NPCs.

## Architecture Layers

1. **LLM Component (Base Model Manager)**
   - **File**: `Assets/LLMUnity/Runtime/LLM.cs`
   - Loads the **single base GGUF** at startup via `CreateServiceAsync()`.
   - Manages corresponding LoRA weights and provides the `SetLoraWeights(Dictionary)` method to switch active LoRA weights safely at runtime.
2. **LoraRegistry & LoraHelper**
   - **Files**: `Assets/LLMUnity/Scripts/NPC/LoraRegistry.cs`, `LoraHelper.cs`
   - Registers LoRA paths on the LLM, managing the activation and deactivation of LoRAs by index or path, using a type-safe list.
3. **NPCLoraLoader (Scene-Level Registration)**
   - **File**: `Assets/LLMUnity/Scripts/NPC/NPCLoraLoader.cs`
   - Scans scene for all `NPCLoraAgent` components and registers each NPC's LoRA with the LLM before conversation starts, and validates all configurations.
4. **NPCLoraAgent (Per-NPC Behavior)**
   - **File**: `Assets/LLMUnity/Scripts/NPC/NPCLoraAgent.cs`
   - Responsible for auto-activating LoRA before chatting, applying system prompts, and exporting metrics.

## NPC Tools and Setup Workflow

We have streamlined NPC creation and configuration to eliminate manual errors and drastically speed up setup.

### Automated Setup Workflow
1. Edit spec JSON in `data/npcs/specs/<npc>.json`.
2. Run: **Assets > LLMUnity > Import NPC Profiles from Specs** (Generates NpcProfile assets).
3. Select an NpcProfile and Run: **Assets > LLMUnity > Create NPC Prefab from Profile** (Creates fully configured prefab).
4. Drag prefab into the scene.

### Key Tools
- **NpcProfile ScriptableObject**: Single source of truth for NPC identity, config, and metadata.
- **LoRA Path Dropdown**: In the inspector, browse available LoRAs with built-in validation for missing files (`[MISSING]` warning).
- **NPC Hot-Reload**: Live update NPC configs without restarting Unity. Run **Assets > LLMUnity > Reload NPC Configurations**.
- **Conversation History Export & Metrics**: `NPCLoraAgent` automatically tracks and provides exports of conversation statistics (latency, tokens, lengths).
- **NPC Profiler**: Track performance metrics. Outputs ranking and averages dynamically using `NpcProfiler.Instance`.

## Folder Structure

```text
Assets/
├── LLMUnity/
│   ├── Scripts/NPC/
│   │   ├── NPCLoraAgent.cs, NPCLoraLoader.cs, NpcProfile.cs, LoraRegistry.cs, NpcProfiler.cs
│   └── Editor/
│       ├── NpcProfileImporter.cs, NpcPrefabFactory.cs, LoraPathDrawer.cs, NpcHotReload.cs
├── Resources/
│   └── NpcProfiles/          <- Profiles auto-created by importer
├── Prefabs/
│   └── NPCs/                 <- Prefabs auto-created by factory
└── StreamingAssets/
    └── Models/               <- Base GGUF + LoRA GGUFs
```

## Validation Checklist
- [ ] Spec JSON files have required fields.
- [ ] Profiles generated via `Import NPC Profiles from Specs`.
- [ ] Prefabs generated via `Create All NPC Prefabs`.
- [ ] Validated via `Validate NPC Configurations in Scene`.
- [ ] LoRA `.gguf` files present in `StreamingAssets/Models/`.
