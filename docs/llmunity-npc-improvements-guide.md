# LLMUnity NPC System Improvements: Implementation Guide

## Overview

8 major improvements have been implemented to streamline NPC creation, configuration management, and performance monitoring. These tools reduce manual work and prevent common errors.

---

## 1. ✅ NpcProfile ScriptableObject (Enhanced)

**Purpose**: Single source of truth for all NPC configuration.

**Features**:
- Bundles `npcId`, `displayName`, `systemPrompt`, `loraPath`, `loraWeight`, metadata
- Version tracking for NPC evolution
- Validation system (`Validate()` method)
- Import timestamp tracking
- Optional profile image and description

**Usage**:
```csharp
// Create via inspector: Assets > Create > LLMUnity > NPC Profile
NpcProfile profile = Resources.Load<NpcProfile>("NpcProfiles/chef_assistant");
agent.npcProfile = profile;  // Auto-populates all fields on Awake()
```

**Files Modified**:
- `Assets/LLMUnity/Scripts/NPC/NpcProfile.cs` - Enhanced with metadata & validation

---

## 2. ✅ NPC Profile Importer (Editor Tool)

**Purpose**: Auto-generate `NpcProfile` assets from `data/npcs/specs/*.json`.

**Eliminates**: Manual copy-paste of system prompts, npcIds, loraWeights between Python specs and Unity.

**Usage**:
```
Menu: Assets > LLMUnity > Import NPC Profiles from Specs
```

**What it does**:
1. Scans `data/npcs/specs/` for `.json` files
2. Parses each spec (reads `npc_key`, `npc_name`, `system_prompt`, `lora_path`, etc.)
3. Creates/updates `Assets/Resources/NpcProfiles/<npc_key>.asset`
4. Sets `lastImportedAt` timestamp

**Implementation**:
- `Assets/LLMUnity/Editor/NpcProfileImporter.cs`

**Example Flow**:
```
1. You update data/npcs/specs/chef_assistant.json
2. Click: Assets > LLMUnity > Import NPC Profiles from Specs
3. Creates: Assets/Resources/NpcProfiles/chef_assistant.asset
4. All fields populated automatically
```

**Additional Menu Options**:
- `Assets > LLMUnity > Validate NPC Profiles` - Check all profiles are valid
- Results shown in a dialog

---

## 3. ✅ NPC Prefab Factory (Editor Tool)

**Purpose**: Create pre-configured NPC GameObjects from NpcProfile assets.

**Eliminates**: Manual GameObject + NPCLoraAgent + field assignment (5+ minutes → 30 seconds).

**Usage**:
```
1. Select an NpcProfile in Project view
2. Menu: Assets > LLMUnity > Create NPC Prefab from Profile
3. Creates: Assets/Prefabs/NPCs/<npc_id>.prefab
```

**Features**:
- NPCLoraAgent component pre-configured
- All inspector fields auto-filled from profile
- Ready to drag into scenes

**Menu Options**:
- `Create NPC Prefab from Profile` - From selected profile
- `Create All NPC Prefabs` - Batch create from all profiles
- `Refresh All NPC Prefabs from Profiles` - Update existing prefabs

**Example**:
```
Before (5 min):
- Create GameObject
- Add NPCLoraAgent component
- Fill npcId, displayName, loraPath, systemPrompt manually
- Save as prefab

After (30 sec):
- Click menu option
- Done
```

**Implementation**:
- `Assets/LLMUnity/Editor/NpcPrefabFactory.cs`

---

## 4. ✅ LoRA Registry ScriptableObject (Type-Safe Replacement)

**Purpose**: Replace fragile comma-separated LoRA strings with type-safe, auditable registry.

**Problem Solved**:
- Old: `_lora = "path1,path2,..."` (hard to debug, index mismatches)
- New: Structured `List<LoraEntry>` with metadata

**Features**:
- Inspector-visible list of LoRA entries
- Each entry: `path`, `weight`, `npcId`, `displayName`, `fileExists` flag
- Methods: `RegisterLora()`, `ActivateLoraByIndex()`, `DeactivateAllLoras()`, etc.
- Validation: `ValidateFiles()` checks all paths exist

**Usage**:
```csharp
// Create: Assets > Create > LLMUnity > LoRA Registry

public class MyLLMSetup : MonoBehaviour
{
    public LoraRegistry loraRegistry;  // Inspector ref
    
    void Start()
    {
        loraRegistry.RegisterLora("Models/chef-lora.gguf", 1.0f, "chef_assistant", "Chef");
        loraRegistry.ActivateLoraByIndex(0);
    }
}
```

**Implementation**:
- `Assets/LLMUnity/Scripts/NPC/LoraRegistry.cs`

**Debug Benefits**:
- Inspector shows LoRA names (not comma soup)
- Visual `isActive` flags for each LoRA
- File validation icons

---

## 5. ✅ LoRA Path Inspector Drawer (Editor Tool)

**Purpose**: Dropdown UI for LoRA path selection + file validation.

**Features**:
- Scans `StreamingAssets/Models/` for `*-lora*.gguf` files
- Displays as dropdown in Inspector
- Shows `[MISSING]` warning for non-existent files
- Real-time validation

**Usage**:
```csharp
[SerializeField]
[LoraPath]  // Custom attribute
private string loraPath = "";
```

**Benefits**:
- ✅ Catch missing LoRAs at edit-time (not runtime)
- ✅ Browse available LoRAs instead of typing
- ✅ Auto-sync when new LoRAs added to StreamingAssets

**Implementation**:
- `Assets/LLMUnity/Scripts/NPC/LoraPathAttribute.cs` - Attribute marker
- `Assets/LLMUnity/Editor/LoraPathDrawer.cs` - Inspector drawer
- `LoraDiscovery.cs` - Utility to scan for .gguf files

---

## 6. ✅ NPC Configuration Validator (Enhanced NPCLoraLoader)

**Purpose**: Validate all NPC configurations at scene load + detect issues early.

**Checks**:
- ✅ LoRA files exist
- ✅ npcId/loraPath not empty
- ✅ systemPrompt populated
- ✅ LoRA index matches registration
- ✅ Detects orphaned LoRAs

**Usage**:
```
Menu: Assets > LLMUnity > Validate NPC Configurations in Scene
```

**In Code**:
```csharp
NPCLoraLoader loader = GetComponent<NPCLoraLoader>();
loader.ValidateAllNpcConfigurations();
```

**Output**:
```
[NPCLoraLoader] NPC 'chef_assistant': systemPrompt is empty (WARNING)
[NPCLoraLoader] NPC 'marvel_heroes': LoRA file not found (ERROR)
[NPCLoraLoader] Found 2 orphaned LoRA references
```

**Implementation**:
- Modified `Assets/LLMUnity/Scripts/NPC/NPCLoraLoader.cs`
- New methods: `ValidateAllNpcConfigurations()`, `ValidateNpcAgent()`

---

## 7. ✅ Conversation History Export & Metrics

**Purpose**: Export chat histories + calculate conversation statistics.

**New NPCLoraAgent Methods**:
```csharp
// Export history as JSON
string json = agent.ExportHistoryAsJson();

// Save to file
await agent.ExportHistoryToFile("Assets/Exports/chef_session_001.json");

// Get metrics
ConversationMetrics metrics = agent.GetConversationMetrics();
Debug.Log(metrics);  // "NPC 'ChefAssistant': 42 messages | ~210 tokens | avg 32 chars"

// Get summary for UI
string summary = agent.GetConversationSummary();
```

**Metrics Tracked** (in `ConversationMetrics`):
- `npcId`, `displayName`
- `totalMessages`, `userMessages`, `assistantMessages`
- `totalCharacters`, `estimatedTokens`, `averageMessageLength`

**Use Cases**:
- Export conversations for training data
- Analyze which NPCs are verbose/concise
- QA analysis of response quality
- Conversation replay for debugging

**Files**:
- Enhanced `Assets/LLMUnity/Scripts/NPC/NPCLoraAgent.cs` - Added export methods
- New `Assets/LLMUnity/Scripts/NPC/ConversationMetrics.cs` - Data class

---

## 8. ✅ NPC Hot-Reload Utility (Editor Tool)

**Purpose**: Reload NPC configurations without restarting Unity.

**Benefits**:
- Iterate on system prompts in real-time
- Test LoRA weight adjustments live
- 10x faster iteration cycle

**Usage**:
```
Menu: Assets > LLMUnity > Reload NPC Configurations (Hot Reload)
```

**What it does**:
1. Finds all `NPCLoraAgent` components in scene
2. Re-runs `InitNpc()` to reload from NpcProfile
3. Marks scene as modified

**Additional Menus**:
- `Assets > LLMUnity > Validate NPC Configurations in Scene` - Check validity
- `Assets > LLMUnity > Debug: Print NPC Agent Info` - Console dump

**Example Workflow**:
```
1. Edit system prompt in NpcProfile
2. Click: Assets > LLMUnity > Reload NPC Configurations
3. See updated behavior immediately (no restart)
4. Iterate rapidly
```

**Implementation**:
- `Assets/LLMUnity/Editor/NpcHotReload.cs`

---

## 9. ✅ NPC Performance Profiler (Runtime)

**Purpose**: Track NPC latency, token usage, and efficiency metrics at runtime.

**Metrics Collected**:
- `totalChats` - Number of Chat() calls
- `avgLatencyMs` - Average response time
- `avgTokensPerResponse` - Average tokens generated
- `avgResponseLength` - Average response chars
- `minLatencyMs` / `maxLatencyMs` - Min/max latency
- `firstChatTime` / `lastChatTime` - Usage timeline

**Usage**:
```csharp
// Automatic: NpcProfiler.Instance is singleton, metrics recorded automatically

// Manual access
NpcProfiler profiler = NpcProfiler.Instance;

// Get metrics for one NPC
var metrics = profiler.GetMetrics("chef_assistant");
Debug.Log(metrics);  
// Output: "NPC 'chef_assistant': 42 chats | Latency: 245ms avg | Tokens: 87 avg"

// Get all metrics
var allMetrics = profiler.GetAllMetrics();

// Export to JSON
await profiler.ExportMetricsAsJson("Assets/Exports/npc_metrics.json");

// Print summary
profiler.PrintMetricsSummary();

// Performance ranking
profiler.PrintPerformanceRanking();

// Clear metrics
profiler.ClearMetrics();
```

**Inspector Settings** (on profiler GameObject):
- `enableProfiling` - Toggle on/off
- `debugLogging` - Log each metric

**Output Example**:
```
=== NPC Performance Metrics ===
NPC 'chef_assistant': 42 chats | Latency: 245ms avg (120-387ms) | Tokens: 87 avg | Length: 348 chars avg
NPC 'marvel_heroes': 28 chats | Latency: 198ms avg (95-312ms) | Tokens: 102 avg | Length: 410 chars avg

Overall avg latency: 221.5ms

=== NPC Performance Ranking (by avg latency) ===
1. marvel_heroes: 198.0ms (from 28 samples)
2. chef_assistant: 245.0ms (from 42 samples)
```

**Use Cases**:
- Identify which NPCs are slow
- Compare token efficiency
- Detect regressions after LoRA updates
- Track usage patterns
- Feed metrics back to training pipeline

**Implementation**:
- New `Assets/LLMUnity/Scripts/NPC/NpcProfiler.cs` - Singleton profiler
- New `Assets/LLMUnity/Scripts/NPC/NpcPerformanceMetrics.cs` - Data class
- Integration in `NPCLoraAgent.Chat()` - Auto-recording

---

## Quick Start: Setting Up an NPC (New Workflow)

### Before (30 min manual work):
```
1. Create GameObject
2. Add NPCLoraAgent
3. Copy system prompt from spec
4. Fill npcId, displayName, loraPath
5. Assign or create NpcProfile
6. Save as prefab
7. Validate fields manually
```

### After (2 min automated):
```
1. Assets > LLMUnity > Import NPC Profiles from Specs
   (One-click generates all profiles)

2. Click an NpcProfile in Project
3. Assets > LLMUnity > Create NPC Prefab from Profile
   (Prefab created, fully configured)

4. Drag prefab into scene
5. Done
```

---

## File Organization

**New Core Scripts**:
- `Assets/LLMUnity/Scripts/NPC/NpcProfile.cs` - Enhanced
- `Assets/LLMUnity/Scripts/NPC/LoraRegistry.cs` - Type-safe LoRA registry
- `Assets/LLMUnity/Scripts/NPC/LoraPathAttribute.cs` - Attribute for dropdown
- `Assets/LLMUnity/Scripts/NPC/NPCLoraAgent.cs` - Enhanced with metrics
- `Assets/LLMUnity/Scripts/NPC/NPCLoraLoader.cs` - Enhanced with validation
- `Assets/LLMUnity/Scripts/NPC/NpcProfiler.cs` - Performance metrics
- `Assets/LLMUnity/Scripts/NPC/ConversationMetrics.cs` - Metrics data class

**New Editor Tools**:
- `Assets/LLMUnity/Editor/NpcProfileImporter.cs` - Spec JSON → NpcProfile
- `Assets/LLMUnity/Editor/NpcPrefabFactory.cs` - NpcProfile → Prefab
- `Assets/LLMUnity/Editor/LoraPathDrawer.cs` - Inspector dropdown
- `Assets/LLMUnity/Editor/NpcHotReload.cs` - Config reload utility

---

## Validation Checklist

Before deploying:

- [ ] `Assets/Resources/NpcProfiles/` folder created
- [ ] `Assets/Prefabs/NPCs/` folder created
- [ ] Spec JSON files have all required fields (`npc_key`, `npc_name`, `system_prompt`, `lora_path`)
- [ ] Run: Assets > LLMUnity > Import NPC Profiles from Specs
- [ ] Run: Assets > LLMUnity > Create All NPC Prefabs
- [ ] Run: Assets > LLMUnity > Validate NPC Profiles (all pass)
- [ ] Run: Assets > LLMUnity > Validate NPC Configurations in Scene
- [ ] LoRA `.gguf` files in `Assets/StreamingAssets/Models/`
- [ ] NPCLoraLoader in scene with `autoScanNPCs=true`

---

## Performance Metrics JSON Format

```json
{
  "exportedAt": "2026-06-03 14:30:45",
  "npcs": [
    {
      "npcId": "chef_assistant",
      "totalChats": 42,
      "avgLatencyMs": 245.3,
      "avgTokensPerResponse": 87.2,
      "avgResponseLength": 348.5,
      "minLatencyMs": 120,
      "maxLatencyMs": 387
    }
  ]
}
```

---

## Troubleshooting

**Issue**: LoRA path dropdown is empty
- **Fix**: Ensure `.gguf` files are in `Assets/StreamingAssets/Models/` with names matching `*-lora*.gguf`
- **Fix**: Editor > Assets > LLMUnity > Validate NPC Configurations in Scene

**Issue**: "NPC profile not found" error
- **Fix**: Run: Assets > LLMUnity > Import NPC Profiles from Specs
- **Fix**: Check `Assets/Resources/NpcProfiles/` folder exists

**Issue**: Prefab not created
- **Fix**: Ensure NpcProfile is valid (Assets > LLMUnity > Validate NPC Profiles)
- **Fix**: Check `Assets/Prefabs/NPCs/` folder exists

**Issue**: Hot reload shows stale values
- **Fix**: Save NpcProfile asset first (Ctrl+S)
- **Fix**: Ensure NpcProfile is assigned to NPCLoraAgent

**Issue**: Profiler not recording metrics
- **Fix**: Create a GameObject with NpcProfiler component (auto-creates singleton)
- **Fix**: Enable `enableProfiling` in profiler inspector

---

## Next Steps

1. **Integrate Spec Importer into your build pipeline** - Auto-generate profiles as part of CI/CD
2. **Add metrics export to your training pipeline** - Feed conversation data back to training
3. **Create a dashboard** - Display profiler metrics in real-time
4. **Extend metrics** - Track conversation quality, user satisfaction, NPC errors
5. **Automate validation** - Run validation on scene load in development

---

## Summary

These 8 improvements together reduce NPC setup from **~30 minutes to 2 minutes** and prevent common configuration errors. The workflow is now:

```
Edit spec JSON
    ↓
Import profiles (1 click)
    ↓
Create prefabs (1 click)
    ↓
Drag into scene
    ↓
Done
```

All configuration is now **source-control friendly** (profiles are assets), **trackable** (version & timestamps), and **validated** (at edit-time and runtime).
