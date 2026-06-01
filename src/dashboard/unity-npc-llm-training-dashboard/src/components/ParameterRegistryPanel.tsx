import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Search,
  RotateCcw,
  Edit3,
  Save,
  X,
  SlidersHorizontal,
  Variable,
  Hash,
  ToggleLeft,
  List,
  CheckSquare,
  AlertTriangle,
  RefreshCw,
  Terminal,
  Settings,
  Layers,
  Zap,
  Cpu,
  HardDrive,
  Globe,
  Box,
} from "lucide-react";
import { cn } from "../lib/utils";
import { Card } from "./Card";
import { LoadingSpinner } from "./LoadingSpinner";
import { EmptyState } from "./EmptyState";

// ── Types ────────────────────────────────────────────────────────────────────

interface ParamDefinition {
  type: string;
  default: unknown;
  min?: number;
  max?: number;
  stage: string;
  description: string;
  tooltip?: string;
  resource_impact: string;
  cli_flag?: string;
  aliases?: string[];
  choices?: unknown[];
  presets?: Record<string, unknown>;
  multiple?: boolean;
  resource_notes?: string;
}

interface EnvVarDefinition {
  type: string;
  default: unknown;
  min?: number;
  max?: number;
  description: string;
  tooltip?: string;
  resource_impact?: string;
  resource_notes?: string;
  choices?: unknown[];
}

/** Minimal param info needed by the inline editor — type + choices. */
interface InlineEditorParam {
  type: string;
  choices?: unknown[];
}

interface ParameterRegistry {
  parameters: Record<string, ParamDefinition>;
  env_vars?: Record<string, EnvVarDefinition>;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const STAGE_ORDER = [
  "generation",
  "sanitize",
  "deepeval",
  "training",
  "export",
  "evaluation",
  "feedback",
  "preflight",
  "global",
] as const;

const STAGE_LABELS: Record<string, string> = {
  generation: "Generation",
  sanitize: "Sanitize",
  deepeval: "DeepEval",
  training: "Training",
  export: "Export",
  evaluation: "Evaluation",
  feedback: "Feedback",
  preflight: "Preflight",
  global: "Global",
};

const TYPE_COLORS: Record<string, string> = {
  float: "text-cyan-400 bg-cyan-400/10 border-cyan-400/30",
  int: "text-blue-400 bg-blue-400/10 border-blue-400/30",
  bool: "text-emerald-400 bg-emerald-400/10 border-emerald-400/30",
  str: "text-violet-400 bg-violet-400/10 border-violet-400/30",
  choice: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  multi_choice: "text-rose-400 bg-rose-400/10 border-rose-400/30",
};

const IMPACT_COLORS: Record<string, string> = {
  none: "text-ink/30 bg-ink/5 border-ink/10",
  cpu: "text-yellow-400 bg-yellow-400/10 border-yellow-400/30",
  disk: "text-orange-400 bg-orange-400/10 border-orange-400/30",
  vram_linear: "text-pink-400 bg-pink-400/10 border-pink-400/30",
};

const IMPACT_LABELS: Record<string, string> = {
  none: "None",
  cpu: "CPU",
  disk: "Disk I/O",
  vram_linear: "VRAM",
};

function formatDefault(value: unknown): string {
  if (value === "") return `""`;
  if (value === undefined || value === null) return "—";
  return String(value);
}

function formatCliFlag(flag?: string): string {
  return flag || "";
}

// ── Sub-components ───────────────────────────────────────────────────────────

function ResourceImpactBadge({ impact }: { impact: string }) {
  const cls = IMPACT_COLORS[impact] || IMPACT_COLORS.none;
  const label = IMPACT_LABELS[impact] || impact;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border",
        cls,
      )}
    >
      {impact === "vram_linear" ? <Zap className="w-2.5 h-2.5" /> : impact === "cpu" ? <Cpu className="w-2.5 h-2.5" /> : impact === "disk" ? <HardDrive className="w-2.5 h-2.5" /> : <Box className="w-2.5 h-2.5" />}
      {label}
    </span>
  );
}

function TypeBadge({ type }: { type: string }) {
  const cls = TYPE_COLORS[type] || TYPE_COLORS.str;
  const Icon = type === "float" || type === "int" ? Hash : type === "bool" ? ToggleLeft : type === "choice" ? List : type === "multi_choice" ? CheckSquare : Variable;
  return (
    <span className={cn("inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border", cls)}>
      <Icon className="w-2.5 h-2.5" />
      {type}
    </span>
  );
}

function InlineEditor({
  value,
  param,
  onSave,
  onCancel,
}: {
  value: string;
  param: InlineEditorParam;
  onSave: (val: string) => void;
  onCancel: () => void;
}) {
  const [editValue, setEditValue] = useState(value);

  // ── Bool: checkbox toggle ──
  if (param.type === "bool") {
    const isChecked = editValue === "true";
    return (
      <div className="flex items-center gap-2 mt-2">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={isChecked}
            onChange={(e) => setEditValue(String(e.target.checked))}
            className="w-4 h-4 accent-accent"
          />
          <span className="text-[12px] text-ink/60">{isChecked ? "true" : "false"}</span>
        </label>
        <button
          onClick={() => onSave(editValue)}
          className="p-1 bg-accent text-bg rounded hover:brightness-110 transition-colors"
          title="Save"
        >
          <Save className="w-3 h-3" />
        </button>
        <button
          onClick={onCancel}
          className="p-1 bg-line/20 text-ink/60 rounded hover:bg-line/40 transition-colors"
          title="Cancel"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    );
  }

  // ── Choice: dropdown select ──
  if (param.type === "choice" && param.choices && param.choices.length > 0) {
    return (
      <div className="flex items-center gap-2 mt-2">
        <select
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          className="flex-1 bg-bg border border-accent/50 rounded px-2 py-1 text-[12px] font-mono text-ink-bright focus:outline-none focus:border-accent"
          autoFocus
          onKeyDown={(e) => {
            if (e.key === "Escape") onCancel();
          }}
        >
          {param.choices.map((choice) => (
            <option key={String(choice)} value={String(choice)}>
              {String(choice)}
            </option>
          ))}
        </select>
        <button
          onClick={() => onSave(editValue)}
          className="p-1 bg-accent text-bg rounded hover:brightness-110 transition-colors"
          title="Save"
        >
          <Save className="w-3 h-3" />
        </button>
        <button
          onClick={onCancel}
          className="p-1 bg-line/20 text-ink/60 rounded hover:bg-line/40 transition-colors"
          title="Cancel"
        >
          <X className="w-3 h-3" />
        </button>
      </div>
    );
  }

  // ── Number / Text: type-aware input ──
  const isNumber = param.type === "int" || param.type === "float";
  const step = param.type === "float" ? "any" : "1";

  return (
    <div className="flex items-center gap-2 mt-2">
      <input
        type={isNumber ? "number" : "text"}
        step={isNumber ? step : undefined}
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        className="flex-1 bg-bg border border-accent/50 rounded px-2 py-1 text-[12px] font-mono text-ink-bright focus:outline-none focus:border-accent"
        autoFocus
        onKeyDown={(e) => {
          if (e.key === "Enter") onSave(editValue);
          if (e.key === "Escape") onCancel();
        }}
      />
      <button
        onClick={() => onSave(editValue)}
        className="p-1 bg-accent text-bg rounded hover:brightness-110 transition-colors"
        title="Save"
      >
        <Save className="w-3 h-3" />
      </button>
      <button
        onClick={onCancel}
        className="p-1 bg-line/20 text-ink/60 rounded hover:bg-line/40 transition-colors"
        title="Cancel"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export function ParameterRegistryPanel() {
  const [registry, setRegistry] = useState<ParameterRegistry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeStage, setActiveStage] = useState<string>(STAGE_ORDER[0]);
  const [searchQuery, setSearchQuery] = useState("");
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [editingParam, setEditingParam] = useState<string | null>(null);

  // ── Fetch registry ──────────────────────────────────────────────────
  const fetchRegistry = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/parameters");
      if (!res.ok) {
        if (res.status === 404) throw new Error("Parameter registry not found on server");
        throw new Error(`Server error: ${res.status}`);
      }
      const data: ParameterRegistry = await res.json();
      if (!data || !data.parameters) {
        throw new Error("Invalid registry format: missing 'parameters' key");
      }
      setRegistry(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load parameter registry");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRegistry();
  }, []);

  // ── Compute stage counts ────────────────────────────────────────────
  const stageCounts = useMemo(() => {
    if (!registry?.parameters) return {};
    const counts: Record<string, number> = {};
    for (const param of Object.values(registry.parameters)) {
      const stage = param.stage || "unknown";
      counts[stage] = (counts[stage] || 0) + 1;
    }
    return counts;
  }, [registry]);

  // ── Filtered params for active stage ────────────────────────────────
  const filteredParams = useMemo(() => {
    if (!registry?.parameters) return [];
    const entries = Object.entries(registry.parameters).filter(
      ([, p]) => p.stage === activeStage,
    );

    if (!searchQuery.trim()) return entries;

    const q = searchQuery.toLowerCase();
    return entries.filter(([key, p]) => {
      const nameMatch = key.toLowerCase().includes(q);
      const descMatch = p.description?.toLowerCase().includes(q) ?? false;
      const tooltipMatch = p.tooltip?.toLowerCase().includes(q) ?? false;
      const cliMatch = p.cli_flag?.toLowerCase().includes(q) ?? false;
      return nameMatch || descMatch || tooltipMatch || cliMatch;
    });
  }, [registry, activeStage, searchQuery]);

  // ── Handlers ────────────────────────────────────────────────────────
  const handleOverride = (paramKey: string, value: string) => {
    let parsedValue: unknown = value;
    const param = registry?.parameters[paramKey];
    if (param) {
      if (param.type === "int") parsedValue = parseInt(value, 10);
      else if (param.type === "float") parsedValue = parseFloat(value);
      else if (param.type === "bool") parsedValue = value === "true";
    } else {
      const envKey = paramKey.startsWith("env:") ? paramKey.slice(4) : "";
      const env = registry?.env_vars?.[envKey];
      if (env) {
        if (env.type === "int") parsedValue = parseInt(value, 10);
        else if (env.type === "float") parsedValue = parseFloat(value);
        else if (env.type === "bool") parsedValue = value === "true";
      }
    }
    setOverrides((prev) => ({ ...prev, [paramKey]: parsedValue }));
    setEditingParam(null);
  };

  const handleResetStage = (stage: string) => {
    if (!registry?.parameters) return;
    const next = { ...overrides };
    for (const [key, p] of Object.entries(registry.parameters)) {
      if (p.stage === stage && next[key] !== undefined) {
        delete next[key];
      }
    }
    setOverrides(next);
  };

  const handleResetAll = () => {
    setOverrides({});
  };

  // ── Loading state ───────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <LoadingSpinner size="lg" label="Loading parameter registry..." />
      </div>
    );
  }

  // ── Error state ─────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8">
        <AlertTriangle className="w-10 h-10 text-danger mb-4" />
        <div className="text-sm font-bold text-danger mb-2">Failed to Load Parameter Registry</div>
        <div className="text-[12px] text-ink/60 mb-4 text-center max-w-md">{error}</div>
        <button
          onClick={fetchRegistry}
          className="flex items-center gap-2 px-4 py-2 bg-accent text-bg text-[12px] font-bold rounded hover:brightness-110 transition-all"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Retry
        </button>
      </div>
    );
  }

  // ── Guard: no data ──────────────────────────────────────────────────
  if (!registry?.parameters || Object.keys(registry.parameters).length === 0) {
    return (
      <EmptyState
        icon={<SlidersHorizontal className="w-12 h-12" />}
        title="No parameters found"
        description="The parameter registry is empty or could not be parsed."
      />
    );
  }

  const sortedStages = STAGE_ORDER.filter((s) => stageCounts[s] > 0);
  const totalOverrides = Object.keys(overrides).length;
  const currentStageOverrides = Object.keys(overrides).filter((key) => {
    const p = registry.parameters[key];
    return p && p.stage === activeStage;
  }).length;

  return (
    <motion.div
      key="parameters"
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 10 }}
      className="flex-1 flex flex-col overflow-hidden min-h-0 min-w-0"
    >
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {/* ── Stage Tabs ─────────────────────────────────────────────────── */}
        <div className="sticky top-0 z-10 bg-bg/80 backdrop-blur-xl border-b border-line">
          <div className="flex items-center justify-between px-4 pt-3 pb-2">
            <div className="flex items-center gap-3">
              <SlidersHorizontal className="w-4 h-4 text-accent" />
              <h3 className="text-[11px] font-bold text-ink-bright uppercase tracking-widest">
                Parameter Registry
              </h3>
              <span className="text-[10px] text-ink/40 font-mono">
                {Object.keys(registry.parameters).length} params
              </span>
              {totalOverrides > 0 && (
                <span className="text-[10px] text-warning font-mono">
                  {totalOverrides} override{totalOverrides !== 1 ? "s" : ""}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {totalOverrides > 0 && (
                <button
                  onClick={handleResetAll}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-ink/50 hover:text-danger border border-line/30 hover:border-danger/30 rounded transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset All
                </button>
              )}
              {currentStageOverrides > 0 && (
                <button
                  onClick={() => handleResetStage(activeStage)}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] font-bold text-ink/50 hover:text-warning border border-line/30 hover:border-warning/30 rounded transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset Stage
                </button>
              )}
            </div>
          </div>

          <div className="flex overflow-x-auto no-scrollbar px-4 gap-1">
            {sortedStages.map((stage) => {
              const count = stageCounts[stage] || 0;
              const isActive = activeStage === stage;
              const hasOverrides = Object.keys(overrides).some((key) => {
                const p = registry.parameters[key];
                return p && p.stage === stage;
              });
              return (
                <button
                  key={stage}
                  onClick={() => setActiveStage(stage)}
                  className={cn(
                    "shrink-0 px-3 py-2 text-[11px] font-bold uppercase tracking-wider border-b-2 transition-all duration-200 relative flex items-center gap-2",
                    isActive
                      ? "border-accent text-ink-bright"
                      : "border-transparent text-ink/30 hover:text-ink/60 hover:border-ink/20",
                  )}
                >
                  {STAGE_LABELS[stage] || stage}
                  <span
                    className={cn(
                      "text-[10px] font-mono px-1.5 py-0.5 rounded-full",
                      isActive
                        ? "bg-accent/15 text-accent"
                        : "bg-line/20 text-ink/40",
                    )}
                  >
                    {count}
                  </span>
                  {hasOverrides && (
                    <span className="w-1.5 h-1.5 rounded-full bg-warning" />
                  )}
                  {isActive && (
                    <motion.div
                      layoutId="paramStageTab"
                      className="absolute inset-0 bg-accent/5 -z-10 rounded-t"
                    />
                  )}
                </button>
              );
            })}
          </div>

          {/* ── Search ──────────────────────────────────────────────────── */}
          <div className="px-4 pb-3 pt-2">
            <div className="relative max-w-md">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-ink/30" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={`Search ${STAGE_LABELS[activeStage] || activeStage} parameters...`}
                className="w-full bg-bg border border-line rounded pl-8 pr-3 py-1.5 text-[12px] text-ink-bright placeholder-ink/20 focus:outline-none focus:border-accent/50 transition-colors"
              />
            </div>
          </div>
        </div>

        {/* ── Parameter Cards ─────────────────────────────────────────────── */}
        <div className="p-4 space-y-3">
          {filteredParams.length === 0 ? (
            <EmptyState
              icon={<Search className="w-8 h-8" />}
              title="No parameters match your search"
              description={
                searchQuery
                  ? `No ${STAGE_LABELS[activeStage] || activeStage} parameters matching "${searchQuery}".`
                  : `No parameters in the ${STAGE_LABELS[activeStage] || activeStage} stage.`
              }
              className="py-16"
            />
          ) : (
            filteredParams.map(([key, param]) => {
              const isEditing = editingParam === key;
              const overrideValue = overrides[key];
              const displayValue = overrideValue !== undefined ? String(overrideValue) : formatDefault(param.default);
              const hasOverride = overrideValue !== undefined;
              const hasPresets = param.presets && Object.keys(param.presets).length > 0;

              return (
                <motion.div
                  key={key}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn(
                    "border rounded p-3 transition-all duration-200",
                    hasOverride
                      ? "border-warning/40 bg-warning/[0.02]"
                      : "border-line/50 bg-surface/20 hover:border-line",
                  )}
                >
                  {/* Header row: name + badges */}
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <code className="text-[13px] font-bold font-mono text-ink-bright truncate">
                        {key}
                      </code>
                      <TypeBadge type={param.type} />
                      <ResourceImpactBadge impact={param.resource_impact || "none"} />
                    </div>
                    <button
                      onClick={() => setEditingParam(isEditing ? null : key)}
                      className={cn(
                        "shrink-0 p-1 rounded transition-colors",
                        isEditing
                          ? "bg-accent/20 text-accent"
                          : "text-ink/30 hover:text-accent hover:bg-accent/10",
                      )}
                      title="Edit override"
                    >
                      <Edit3 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Description / Tooltip */}
                  <p className="text-[12px] text-ink/60 leading-relaxed mb-2">
                    {param.tooltip || param.description}
                  </p>

                  {/* Details grid */}
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                    {/* Default value */}
                    <div className="flex items-center gap-1.5">
                      <span className="text-ink/40 uppercase tracking-wider text-[10px]">Default</span>
                      <code
                        className={cn(
                          "px-1.5 py-0.5 rounded text-[10px] font-mono",
                          hasOverride
                            ? "bg-line/20 text-ink/50 line-through"
                            : "bg-accent/10 text-accent font-bold",
                        )}
                      >
                        {formatDefault(param.default)}
                      </code>
                    </div>

                    {/* Override value (if set) */}
                    {hasOverride && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-warning uppercase tracking-wider text-[10px]">Override</span>
                        <code className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-warning/10 text-warning font-bold">
                          {String(overrideValue)}
                        </code>
                      </div>
                    )}

                    {/* CLI flag */}
                    {param.cli_flag && (
                      <div className="flex items-center gap-1.5">
                        <Terminal className="w-3 h-3 text-ink/30" />
                        <code className="text-[10px] font-mono text-ink/50">
                          {formatCliFlag(param.cli_flag)}
                        </code>
                      </div>
                    )}

                    {/* Min/Max */}
                    {(param.min !== undefined || param.max !== undefined) && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-ink/40 text-[10px]">Range:</span>
                        <code className="text-[10px] font-mono text-ink/50">
                          {param.min !== undefined ? param.min : "—"} – {param.max !== undefined ? param.max : "—"}
                        </code>
                      </div>
                    )}

                    {/* Choices */}
                    {param.type === "choice" && param.choices && param.choices.length > 0 && (
                      <div className="flex items-center gap-1.5">
                        <span className="text-ink/40 text-[10px]">Choices:</span>
                        <code className="text-[10px] font-mono text-ink/50 truncate max-w-[200px]">
                          {param.choices.join(", ")}
                        </code>
                      </div>
                    )}

                    {/* Resource notes */}
                    {param.resource_notes && (
                      <div className="flex items-center gap-1.5 w-full mt-1">
                        <AlertTriangle className="w-3 h-3 text-ink/20 shrink-0" />
                        <span className="text-[10px] text-ink/40 italic leading-relaxed">
                          {param.resource_notes}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Presets */}
                  {hasPresets && (
                    <div className="mt-2 pt-2 border-t border-line/30">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-[10px] text-ink/30 uppercase tracking-wider font-bold">Presets</span>
                        {Object.entries(param.presets!).map(([presetName, presetVal]) => (
                          <span
                            key={presetName}
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-surface/60 border border-line/30 text-ink/60"
                          >
                            <Layers className="w-2.5 h-2.5" />
                            {presetName}: <span className="text-ink-bright font-bold">{String(presetVal)}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Inline Editor */}
                  {isEditing && (
                    <InlineEditor
                      value={displayValue}
                      param={{ type: param.type, choices: param.choices }}
                      onSave={(val) => handleOverride(key, val)}
                      onCancel={() => setEditingParam(null)}
                    />
                  )}
                </motion.div>
              );
            })
          )}
        </div>

        {/* ── Env Vars Section ─────────────────────────────────────────────── */}
        {registry.env_vars && Object.keys(registry.env_vars).length > 0 && (
          <div className="px-4 pb-6">
            <Card title="Environment Variables" subtitle={`${Object.keys(registry.env_vars).length} vars`}>
              <div className="space-y-3">
                {Object.entries(registry.env_vars).map(([key, env]) => {
                  const isEditing = editingParam === `env:${key}`;
                  const overrideValue = overrides[`env:${key}`];
                  const displayValue = overrideValue !== undefined ? String(overrideValue) : formatDefault(env.default);
                  const hasOverride = overrideValue !== undefined;

                  return (
                    <div
                      key={key}
                      className={cn(
                        "border rounded p-3 transition-all",
                        hasOverride
                          ? "border-warning/40 bg-warning/[0.02]"
                          : "border-line/30",
                      )}
                    >
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <Globe className="w-3.5 h-3.5 text-accent/60 shrink-0" />
                          <code className="text-[12px] font-bold font-mono text-ink-bright">
                            {key}
                          </code>
                          <TypeBadge type={env.type} />
                          {env.resource_impact && (
                            <ResourceImpactBadge impact={env.resource_impact} />
                          )}
                        </div>
                        <button
                          onClick={() => setEditingParam(isEditing ? null : `env:${key}`)}
                          className={cn(
                            "shrink-0 p-1 rounded transition-colors",
                            isEditing
                              ? "bg-accent/20 text-accent"
                              : "text-ink/30 hover:text-accent hover:bg-accent/10",
                          )}
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      <p className="text-[12px] text-ink/60 leading-relaxed mb-2">
                        {env.tooltip || env.description}
                      </p>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
                        <div className="flex items-center gap-1.5">
                          <span className="text-ink/40 uppercase tracking-wider text-[10px]">Default</span>
                          <code
                            className={cn(
                              "px-1.5 py-0.5 rounded text-[10px] font-mono",
                              hasOverride
                                ? "bg-line/20 text-ink/50 line-through"
                                : "bg-accent/10 text-accent font-bold",
                            )}
                          >
                            {formatDefault(env.default)}
                          </code>
                        </div>

                        {hasOverride && (
                          <div className="flex items-center gap-1.5">
                            <span className="text-warning uppercase tracking-wider text-[10px]">Override</span>
                            <code className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-warning/10 text-warning font-bold">
                              {String(overrideValue)}
                            </code>
                          </div>
                        )}

                        {(env.min !== undefined || env.max !== undefined) && (
                          <div className="flex items-center gap-1.5">
                            <span className="text-ink/40 text-[10px]">Range:</span>
                            <code className="text-[10px] font-mono text-ink/50">
                              {env.min !== undefined ? env.min : "—"} – {env.max !== undefined ? env.max : "—"}
                            </code>
                          </div>
                        )}

                        {env.choices && env.choices.length > 0 && (
                          <div className="flex items-center gap-1.5">
                            <span className="text-ink/40 text-[10px]">Choices:</span>
                            <code className="text-[10px] font-mono text-ink/50">
                              {env.choices.join(", ")}
                            </code>
                          </div>
                        )}

                        {env.resource_notes && (
                          <div className="flex items-center gap-1.5 w-full mt-1">
                            <AlertTriangle className="w-3 h-3 text-ink/20 shrink-0" />
                            <span className="text-[10px] text-ink/40 italic">{env.resource_notes}</span>
                          </div>
                        )}
                      </div>

                      {isEditing && (
                        <InlineEditor
                          value={displayValue}
                          param={{ type: env.type, choices: env.choices }}
                          onSave={(val) => handleOverride(`env:${key}`, val)}
                          onCancel={() => setEditingParam(null)}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        )}

        {sortedStages.length === 0 && (
          <EmptyState
            icon={<Settings className="w-10 h-10" />}
            title="No stages available"
            description="The parameter registry does not contain any recognized pipeline stages."
          />
        )}
      </div>
    </motion.div>
  );
}
