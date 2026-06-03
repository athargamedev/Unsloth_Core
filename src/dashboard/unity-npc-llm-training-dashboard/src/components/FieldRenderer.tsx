import { cn } from "../lib/utils";
import { resolveTemplates } from "../lib/resolveTemplates";
import type { CommandFieldSchema } from "../schemas/command-field";

export interface FieldRendererProps {
  fieldPath: string;
  schema?: CommandFieldSchema;
  value: unknown;
  onChange: (fieldPath: string, value: unknown) => void;
  error?: string;
  context?: Record<string, string>;
}

/**
 * Formats a dotted field path into a human-readable label.
 * "options.technique" → "Options → Technique"
 */
function formatLabel(fieldPath: string): string {
  return fieldPath
    .split(".")
    .map((segment) =>
      segment
        .replace(/([A-Z])/g, " $1")
        .replace(/^./, (ch) => ch.toUpperCase())
        .trim(),
    )
    .join(" → ");
}

function resolveIfString(val: unknown, context?: Record<string, string>): unknown {
  if (typeof val === "string" && context) {
    return resolveTemplates(val, context);
  }
  return val;
}

export function FieldRenderer({
  fieldPath,
  schema,
  value,
  onChange,
  error,
  context,
}: FieldRendererProps) {
  if (!schema) return <div className="text-xs text-ink/30 italic">Unknown field: {fieldPath}</div>;
  const description = resolveIfString(schema.description, context) as string | undefined;
  const label = formatLabel(fieldPath);
  const hasValue = value !== undefined && value !== null;

  // ── Shared input classes ────────────────────────────────────────────────
  const inputBase = cn(
    "w-full p-2 bg-bg border border-line rounded text-sm",
    "focus:outline-none focus:border-accent",
    error && "border-danger",
  );

  // ── Render by type ──────────────────────────────────────────────────────

  const renderControl = (): React.ReactNode => {
    switch (schema.type) {
      case "string":
        return renderStringControl();
      case "number":
        return renderNumberControl();
      case "boolean":
        return renderBooleanControl();
      case "path":
        return renderPathControl();
      case "array":
        return renderUnsupported("array");
      default:
        return renderUnsupported(schema.type);
    }
  };

  function renderStringControl(): React.ReactNode {
    // Enum → dropdown
    if (schema.enum && schema.enum.length > 0) {
      return (
        <select
          value={hasValue ? String(value) : ""}
          onChange={(e) => onChange(fieldPath, e.target.value)}
          className={inputBase}
        >
          {!schema.required && <option value="">--</option>}
          {schema.enum.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );
    }

    // Plain text input
    return (
      <input
        type="text"
        value={hasValue ? String(value) : ""}
        onChange={(e) => onChange(fieldPath, e.target.value)}
        className={inputBase}
      />
    );
  }

  function renderNumberControl(): React.ReactNode {
    return (
      <input
        type="number"
        value={hasValue ? String(value) : ""}
        onChange={(e) => {
          const raw = e.target.value;
          onChange(fieldPath, raw === "" ? "" : Number(raw));
        }}
        className={inputBase}
      />
    );
  }

  function renderBooleanControl(): React.ReactNode {
    const { flagType } = schema;

    // BooleanOptionalAction → 3-way select
    if (flagType === "BooleanOptionalAction") {
      const selectValue =
        value === null
          ? "null"
          : value === true
            ? "true"
            : value === false
              ? "false"
              : "null";
      return (
        <select
          value={selectValue}
          onChange={(e) => {
            const v = e.target.value;
            onChange(fieldPath, v === "null" ? null : v === "true");
          }}
          className={inputBase}
        >
          <option value="null">unset / default</option>
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      );
    }

    // store_true → checkbox (checked = true)
    if (flagType === "store_true") {
      const checked = value === true;
      return (
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(fieldPath, e.target.checked)}
          className="w-4 h-4 accent-accent"
        />
      );
    }

    // store_false → checkbox (checked = false, inverted)
    if (flagType === "store_false") {
      // checked when the value IS false (i.e. default / active)
      const checked = value === false || value === undefined || value === null;
      return (
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(fieldPath, !e.target.checked)}
          className="w-4 h-4 accent-accent"
        />
      );
    }

    // Default boolean → plain checkbox
    const checked = value === true;
    return (
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(fieldPath, e.target.checked)}
        className="w-4 h-4 accent-accent"
      />
    );
  }

  function renderPathControl(): React.ReactNode {
    const rootHint =
      schema.roots && schema.roots.length > 0
        ? `${schema.roots.join(", ")}/`
        : undefined;
    return (
      <input
        type="text"
        value={hasValue ? String(value) : ""}
        onChange={(e) => onChange(fieldPath, e.target.value)}
        placeholder={rootHint ?? "Enter path\u2026"}
        className={inputBase}
      />
    );
  }

  function renderUnsupported(type: string): React.ReactNode {
    return (
      <div className="text-xs text-ink/40 italic px-1 py-1.5">
        Unsupported field type: {type}
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {/* Label */}
      <span className="block text-sm font-bold text-ink/60">
        {label}
        {schema.pathType && (
          <span className="ml-1.5 text-[10px] text-accent/60 font-normal">
            ({schema.pathType})
          </span>
        )}
        {schema.required && <span className="text-danger ml-0.5">*</span>}
      </span>

      {/* Control */}
      {renderControl()}

      {/* Error */}
      {error && (
        <span className="block text-sm text-danger mt-1">{error}</span>
      )}

      {/* Description */}
      {!error && description && (
        <span className="block text-[10px] text-ink/40 mt-1">{description}</span>
      )}
    </div>
  );
}
