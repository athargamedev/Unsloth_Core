# LLMUnity Base Model + LoRA Architecture

## Overview

LLMUnity uses a **dual-GGUF strategy**:
- **Single shared base model** (e.g., `llama-3.2-3b-instruct-q4_k_m.gguf`) loaded once at startup
- **Multiple LoRA adapters** (e.g., `chef_assistant-lora-f16.gguf`, `marvel_heroes_instructor-lora-f16.gguf`) registered and switched at runtime

The base model never changes; only LoRA weights are swapped when switching NPCs.

---

## Architecture Layers

### Layer 1: LLM Component (Base Model Manager)
**File**: `Assets/LLMUnity/Runtime/LLM.cs`

**Responsibilities**:
- Loads the **single base GGUF** at startup via `CreateServiceAsync()`
- Manages a **comma-separated registry of all LoRA paths** (`_lora` field)
- Manages corresponding LoRA weights (`_loraWeights` field)
- Provides the `SetLoraWeights(Dictionary)` method to switch active LoRA weights at runtime

**Key Fields**:
```csharp
private string _lora = "";              // "Models/chef-lora.gguf,Models/marvel-lora.gguf,..."
private string _loraWeights = "";       // "1.0,0.5,0.0,..." (one weight per LoRA)
public LoraManager loraManager = ...;   // Parses and manages the above strings
public LLMService llmService = ...;     // C++ bridge to the actual inference engine
```

**Startup Flow** (in `CreateServiceAsync`):
```
1. Validate base model path
2. Get all LoRA paths from loraManager
3. Call LLMService.CreateLLM(baseModelPath, loraPaths[])
   → C++ backend loads base model + all LoRA headers
4. If LLM started successfully:
   - Call ApplyLoras() to set initial weights (all zeros by default)
   - Start server
```

**After startup**, changing LoRA weights is **lock-safe and fast**:
```csharp
public void SetLoraWeights(Dictionary<string, float> loraToWeight)
{
    lock (loraLock)  // Thread-safe
    {
        foreach (var entry in loraToWeight)
        {
            loraManager.SetWeight(entry.Key, entry.Value);  // Update weights dict
        }
        UpdateLoras();  // Sync _lora/_loraWeights strings
        if (started) ApplyLoras();  // Send to C++ backend
    }
}

private void ApplyLoras()
{
    var loras = new List<LoraIdScale>();
    float[] weights = loraManager.GetWeights();
    
    for (int i = 0; i < weights.Length; i++)
    {
        loras.Add(new LoraIdScale(i, weights[i]));
    }
    
    llmService.LoraWeight(loras);  // C++ backend applies weights
}
```

---

### Layer 2: LoraHelper (LoRA Registration & Switching)
**File**: `Assets/LLMUnity/Scripts/NPC/LoraHelper.cs`

**Responsibilities**:
- Register LoRA paths on the LLM before or after startup
- Activate/deactivate LoRAs by index or path
- Manage LoRA lifecycle (add, find, remove, validate files)

**Key Methods**:

#### `AppendLora(LLM, loraPath, weight, validate)`
```csharp
public static int AppendLora(LLM llm, string loraPath, float weight, bool validatePath)
{
    // Check for duplicate
    if (llm.lora contains loraPath) return existingIndex;
    
    // Append to comma-separated strings
    llm.lora = "existing,gguf,...," + loraPath;
    llm.loraWeights = "1.0,0.8,...," + weight;
    
    return newIndex;
}
```
**Called by**: `NPCLoraAgent.RegisterLoraWithLLM()` during NPC init.

#### `ActivateLoraByIndex(LLM, index, weight)`
```csharp
public static bool ActivateLoraByIndex(LLM llm, int index, float weight)
{
    // Build a weight dictionary: all zeros except the target index
    var weights = new Dictionary<string, float>();
    string[] loraPaths = llm.loraManager.GetLoras();
    
    for (int i = 0; i < loraPaths.Length; i++)
        weights[loraPaths[i]] = (i == index) ? weight : 0f;
    
    // Apply to LLM (thread-safe)
    llm.SetLoraWeights(weights);
}
```

#### `ActivateLoraByPath(LLM, loraPath, weight)`
Similar to `ActivateLoraByIndex()` but finds the index first using string matching.

#### `DeactivateAllLoras(LLM)`
```csharp
public static void DeactivateAllLoras(LLM llm)
{
    // Set all weights to 0 → falls back to base model only
    var weights = new Dictionary<string, float>();
    foreach (var path in llm.loraManager.GetLoras())
        weights[path] = 0f;
    
    llm.SetLoraWeights(weights);
}
```

---

### Layer 3: NPCLoraLoader (Scene-Level Registration)
**File**: `Assets/LLMUnity/Scripts/NPC/NPCLoraLoader.cs`

**Responsibilities**:
- Execute at `Awake()` with `ExecutionOrder(-100)` (very early)
- Auto-scan scene for all `NPCLoraAgent` components
- Register each NPC's LoRA with the LLM before conversation starts
- Optionally discover LoRA files from disk

**Execution Flow**:
```
Awake() with ExecutionOrder(-100):
  1. Find or create LLM in scene
  2. Create SupabaseDatabase singleton if config provided
  3. If autoScanNPCs=true:
     - FindObjectsByType<NPCLoraAgent>()
     - For each agent: RegisterNpcAgent(agent)
       → agent.RegisterLoraWithLLM() via LoraHelper.AppendLora()
  4. If autoDiscoverLoras=true:
     - LoraDiscovery.DiscoverLoras("Models/")
     - Register any found .gguf files
```

**Result**: All NPC LoRAs are now registered with the LLM but **all weights are 0** (inactive).

---

### Layer 4: NPCLoraAgent (Per-NPC Behavior)
**File**: `Assets/LLMUnity/Scripts/NPC/NPCLoraAgent.cs`

**Extends**: `LLMAgent` (which extends `LLMClient`)

**Key Fields**:
```csharp
public string npcId = "chef_assistant";                // Unique ID
public string displayName = "ChefAssistant";           // Display name
public string _systemPrompt = "## IDENTITY\n...";     // NPC personality
public string loraPath = "Models/chef-lora-f16.gguf"; // Path to LoRA
public int loraIndex = -1;                            // Index after registration
public float loraWeight = 1.0f;                       // Strength (0..2)
public bool autoActivateLora = true;                 // Auto-activate before Chat()
public bool autoPromptPairing = true;                // Auto-apply system prompt
```

#### Initialization: `Awake()` → `InitNpc()`
```csharp
public override void Awake()
{
    base.Awake();
    InitNpc();
}

protected virtual void InitNpc()
{
    // Apply NpcProfile overrides if assigned
    if (npcProfile != null)
    {
        npcId = npcProfile.npcId;
        displayName = npcProfile.displayName;
        _systemPrompt = npcProfile.systemPrompt;
        loraPath = npcProfile.loraPath;
        loraWeight = npcProfile.loraWeight;
    }
    
    // Set defaults
    if (string.IsNullOrEmpty(npcId))
        npcId = gameObject.name;
    if (string.IsNullOrEmpty(displayName))
        displayName = npcId;
    if (string.IsNullOrEmpty(sessionId))
        sessionId = Guid.NewGuid().ToString();  // One session per NPC instance
    
    // Load past history from Supabase if enabled
    if (useSupabasePersistence && autoLoadHistory)
        await LoadHistoryFromSupabase();  // Called in Start()
}
```

#### LoRA Registration: `RegisterLoraWithLLM()`
```csharp
public virtual void RegisterLoraWithLLM()
{
    if (loraRegistered || llm == null || loraPath.IsNullOrEmpty())
        return;
    
    // Register this NPC's LoRA using LoraHelper
    int index = LoraHelper.AppendLora(llm, loraPath.Trim(), loraWeight, validate: true);
    
    if (index >= 0)
    {
        loraIndex = index;  // Remember index for fast activation
        loraRegistered = true;
        Log($"[NPCLoraAgent] Registered NPC '{npcId}' LoRA at index {loraIndex}: {loraPath}");
    }
}
```
**Called by**: `NPCLoraLoader.RegisterAllNpcAgents()` via `RegisterNpcAgent()`.

#### LoRA Activation: `ActivateLora()`
```csharp
public virtual void ActivateLora()
{
    if (!llm.started) return;
    
    // Activate this NPC's LoRA (all others → weight 0)
    if (loraIndex >= 0)
    {
        LoraHelper.ActivateLoraByIndex(llm, loraIndex, loraWeight);
    }
    else if (!loraPath.IsNullOrEmpty())
    {
        LoraHelper.ActivateLoraByPath(llm, loraPath, loraWeight);
    }
    
    // Apply this NPC's system prompt
    if (autoPromptPairing && !_systemPrompt.IsNullOrEmpty())
    {
        systemPrompt = _systemPrompt;  // LLMAgent property
    }
}
```

#### Chat with Auto-Activation: `Chat()`
```csharp
public override async Task<string> Chat(string query, Action<string> callback = null, ...)
{
    // THIS IS THE KEY: Activate LoRA + system prompt before every Chat
    if (autoActivateLora)
        ActivateLora();  // Sets only this NPC's LoRA to weight, all others to 0
    
    // Augment system prompt with function descriptions if needed
    string originalPrompt = null;
    if (enableFunctionCalling && FunctionRegistry.HasFunctions)
    {
        originalPrompt = _systemPrompt;
        systemPrompt = _systemPrompt + "\n\n" + FunctionRegistry.BuildPromptInstructions();
    }
    
    try
    {
        // Call parent Chat (LLMAgent) → LLMClient → LLMService.Complete()
        result = await base.Chat(query, callback, completionCallback, addToHistory);
    }
    finally
    {
        // Restore original prompt if functions were added
        if (enableFunctionCalling && originalPrompt != null)
            systemPrompt = originalPrompt;
    }
    
    // Multi-round function calling loop if enabled
    if (enableFunctionCalling && FunctionRegistry.HasFunctions)
    {
        for (int round = 0; round < functionCallMaxRounds; round++)
        {
            var call = FunctionRegistry.ParseFunctionCall(result);
            if (call == null) break;
            
            string functionResult = await FunctionRegistry.ExecuteAsync(call.Name, call.Args);
            result = await base.Chat("[System: Function result...]\n" + functionResult, ...);
        }
    }
    
    // Auto-save history to Supabase if enabled
    if (autoSaveHistory && supabase != null)
        await SaveExchangeToSupabase(query, result);
    
    return result;
}
```

---

## How NPC Switching Works (Step by Step)

### Example: Player switches from ChefAssistant to MarvelHeroes

**State at startup** (after `NPCLoraLoader.Awake()`):
```
LLM.lora = "Models/chef_assistant-lora-f16.gguf,Models/marvel_heroes_instructor-lora-f16.gguf"
LLM.loraWeights = "0,0"  // All zero (all deactivated)

chef_agent = NPCLoraAgent(npcId="chef_assistant", loraIndex=0, loraWeight=1.0)
marvel_agent = NPCLoraAgent(npcId="marvel_heroes_instructor", loraIndex=1, loraWeight=1.0)
```

**User calls**: `await chefAgent.Chat("How do I chop an onion?")`
```
1. ActivateLora() is called:
   → LoraHelper.ActivateLoraByIndex(llm, loraIndex=0, weight=1.0)
   → llm.SetLoraWeights({
       "Models/chef_assistant-lora-f16.gguf": 1.0,
       "Models/marvel_heroes_instructor-lora-f16.gguf": 0.0
     })
   → LLM.ApplyLoras() sends [LoraIdScale(0, 1.0), LoraIdScale(1, 0.0)] to C++
   
   → systemPrompt = "## IDENTITY\nName: ChefAssistant | Role: friendly culinary instructor\n..."

2. LLMAgent.Chat() is called:
   → LLMClient.Chat() → LLMService.Complete()
   → C++ backend:
      - Loads base model weights
      - Adds (0.0 * marvel LoRA weights) = no modification
      - Adds (1.0 * chef LoRA weights) = full chef personality
      - Inference with chef-tuned model
   
3. Response: "Slice the onion root-side up, keep the root intact for stability..."

4. History saved to Supabase:
   → supabase.SaveChatMessage("chef_assistant", "user", "How do I chop an onion?", sessionId)
   → supabase.SaveChatMessage("chef_assistant", "assistant", response, sessionId)
```

**User switches**: `await marvelAgent.Chat("Who is Agent Coulson?")`
```
1. ActivateLora() is called:
   → LoraHelper.ActivateLoraByIndex(llm, loraIndex=1, weight=1.0)
   → llm.SetLoraWeights({
       "Models/chef_assistant-lora-f16.gguf": 0.0,
       "Models/marvel_heroes_instructor-lora-f16.gguf": 1.0
     })
   → LLM.ApplyLoras() sends [LoraIdScale(0, 0.0), LoraIdScale(1, 1.0)] to C++
   
   → systemPrompt = "## IDENTITY\nName: Agent Coulson (Instructor) | Role: SHIELD academy instructor\n..."

2. LLMAgent.Chat() is called:
   → C++ backend:
      - Loads base model weights
      - Adds (0.0 * chef LoRA weights) = no modification
      - Adds (1.0 * marvel LoRA weights) = full Marvel personality
      - Inference with Marvel-tuned model
   
3. Response: "Agent Coulson is a SHIELD veteran. Tactical specialist, expert in superhuman threat assessment..."

4. History saved to Supabase:
   → supabase.SaveChatMessage("marvel_heroes_instructor", "user", "Who is Agent Coulson?", sessionId)
   → supabase.SaveChatMessage("marvel_heroes_instructor", "assistant", response, sessionId)
```

**Key insight**: The **base model never changed**. Only LoRA weights were swapped!

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ NPCLoraAgent (MarvelHeroes GameObject)                          │
│ npcId="marvel_heroes_instructor"                                │
│ loraPath="Models/marvel_heroes_instructor-lora-f16.gguf"       │
│ loraIndex=1                                                     │
│ systemPrompt="## IDENTITY\nName: Agent Coulson..."             │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ await Chat("Who is Agent Coulson?")
                     │
                     ▼
         ┌───────────────────────────┐
         │ NPCLoraAgent.Chat()       │
         │ - autoActivateLora=true   │
         └───────────┬───────────────┘
                     │
                     ▼
         ┌──────────────────────────────────────────┐
         │ ActivateLora()                           │
         │ LoraHelper.ActivateLoraByIndex(          │
         │   llm, index=1, weight=1.0)              │
         └───────────┬──────────────────────────────┘
                     │
                     ▼
         ┌────────────────────────────────────────────┐
         │ LLM.SetLoraWeights({                       │
         │   "Models/chef_assistant-lora...": 0.0,   │
         │   "Models/marvel_heroes...-lora...": 1.0  │
         │ })                                         │
         └───────────┬────────────────────────────────┘
                     │
                     ▼
         ┌────────────────────────────────────────────┐
         │ LLM.ApplyLoras()                           │
         │ llmService.LoraWeight([                    │
         │   LoraIdScale(0, 0.0),   // chef: off     │
         │   LoraIdScale(1, 1.0)    // marvel: on    │
         │ ])                                         │
         └───────────┬────────────────────────────────┘
                     │
                     ▼
         ┌────────────────────────────────────────────┐
         │ C++ Backend (llama.cpp)                    │
         │ - Base Model (llama-3.2-3b loaded)        │
         │ - All LoRA headers in VRAM                 │
         │ - Apply weights: output = base +           │
         │   1.0*marvel_lora + 0.0*chef_lora        │
         │ - Inference with Marvel personality       │
         └───────────┬────────────────────────────────┘
                     │
                     ▼
         ┌────────────────────────────────────────────┐
         │ Response: "Agent Coulson is a SHIELD      │
         │ veteran, tactical specialist..."          │
         └────────────────────────────────────────────┘
```

---

## System Prompt Pairing

The `autoPromptPairing` flag (default: **true**) ensures:
1. When `ActivateLora()` is called
2. The NPC's `systemPrompt` is applied to the LLM
3. Every Chat() uses the correct system prompt for the active NPC

**Flow**:
```csharp
// In ActivateLora():
if (autoPromptPairing && !_systemPrompt.IsNullOrEmpty())
{
    systemPrompt = _systemPrompt;  // Propagates to LLMAgent
    // LLMAgent passes it to LLMService.Complete() for every inference
}
```

---

## Performance Optimization: Why This Design?

| Aspect | Benefit |
|--------|---------|
| **Single base model** | Load once (~6GB for 3B model), reuse for all NPCs |
| **LoRA as overlays** | Each LoRA is ~50-200MB; swap weights in milliseconds |
| **Pre-registered LoRAs** | Headers loaded at startup; no file I/O during switches |
| **Lock-free per-NPC** | Each NPC's Chat() is independent; no contention |
| **Slot-based concurrency** | Multiple NPCs can chat in parallel slots |

---

## Configuration Checklist

When setting up a new NPC:

- [ ] **Spec JSON** (`data/npcs/specs/<npc>.json`): Define identity, system prompt, LoRA path
- [ ] **Train & Export LoRA**: Generate `<npc>-lora-f16.gguf`
- [ ] **Place LoRA in StreamingAssets**: `Assets/StreamingAssets/Models/<npc>-lora-f16.gguf`
- [ ] **Create GameObject**: Add `NPCLoraAgent` component
- [ ] **Set Inspector Fields**:
  - `npcId` = spec key
  - `displayName` = human name
  - `systemPrompt` = from spec
  - `loraPath` = `Models/<npc>-lora-f16.gguf`
  - `loraWeight` = 1.0 (or 0.5-2.0 for tuning)
  - `autoActivateLora` = true
  - `autoPromptPairing` = true
- [ ] **Scene NPCLoraLoader**:
  - `targetLLM` = reference to your LLM GameObject
  - `autoScanNPCs` = true
  - `autoActivateLora` in each agent = true
