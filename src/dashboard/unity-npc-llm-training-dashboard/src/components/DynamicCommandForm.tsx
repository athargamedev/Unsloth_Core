import { useMemo } from "react";
import { cn } from "../lib/utils";
import { FieldRenderer } from "./FieldRenderer";
import type { CommandFieldSchema } from "../schemas/command-field";

// Types rendered by FieldRenderer — everything else shows "Unsupported"
const KNOWN_FIELD_TYPES = new Set(["string", "number", "boolean", "path"]);

const SKIP_FIELDS = new Set(["commandId", "type"]);

export interface DynamicCommandFormProps {
  commandId: string;
  fields: Record<string, CommandFieldSchema>;
  values: Record<string, unknown>;
  onChange: (fieldPath: string, value: unknown) => void;
  errors?: Record<string, string>;
  context?: Record<string, string>;
  loading?: boolean;
  onRetry?: () => void;
  /** Only render fields matching these keys (e.g., ["spec", "preset", "options.technique"]) */
  fieldKeys?: readonly string[];
  /** Suppress the Command ID read-only box (for inline usage inside custom layouts) */
  hideCommandId?: boolean;
}

interface SortedField {
  fieldPath: string;
  schema: CommandFieldSchema;
}

/**
 * Renders a full dynamic form from a CommandDefinition's field schemas.
 */
export function DynamicCommandForm({
  commandId,
  fields,
  values,
  onChange,
  errors,
  context,
  loading = false,
  onRetry,
  fieldKeys,
  hideCommandId = false,
}: DynamicCommandFormProps) {
  // ── Sort & filter fields ────────────────────────────────────────────────
  const sortedFields: SortedField[] = useMemo(() => {
    const fieldKeySet = fieldKeys ? new Set(fieldKeys) : null;
    return Object.entries(fields)
      .filter(([key]) => !SKIP_FIELDS.has(key))
      .filter(([fieldPath]) => !fieldKeySet || fieldKeySet.has(fieldPath))
      .map(([fieldPath, schema]) => ({ fieldPath, schema }))
      .sort((a, b) => {
        const orderA = a.schema.order ?? Number.MAX_SAFE_INTEGER;
        const orderB = b.schema.order ?? Number.MAX_SAFE_INTEGER;
        if (orderA !== orderB) return orderA - orderB;
        return a.fieldPath.localeCompare(b.fieldPath);
      });
  }, [fields, fieldKeys]);

  // ── Loading skeleton ────────────────────────────────────────────────────
  if (loading) {
    return <LoadingSkeleton />;
  }

  // ── No fields ───────────────────────────────────────────────────────────
  if (sortedFields.length === 0) {
    return (
      <div className="text-sm text-ink/40 text-center py-6">
        No configurable fields for this command.
      </div>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Command ID (read-only) — hidden when hideCommandId is set */}
      {!hideCommandId && (
        <div className="space-y-1">
          <span className="block text-sm font-bold text-ink/60">Command ID</span>
          <div className="p-2 bg-bg border border-line rounded text-sm font-mono">
            {commandId}
          </div>
        </div>
      )}

      {sortedFields.map(({ fieldPath, schema }) => {
        const value = getNestedValue(values, fieldPath);
        const fieldError = errors?.[fieldPath];

        // Unsupported type guard
        if (!KNOWN_FIELD_TYPES.has(schema.type)) {
          return (
            <div key={fieldPath} className="text-xs text-ink/40 italic px-1 py-1.5 border border-dashed border-line rounded">
              Unsupported field type: {schema.type}
            </div>
          );
        }

        // nargs → show single input with note
        if (schema.nargs !== undefined && schema.nargs !== null) {
          return (
            <div key={fieldPath} className="space-y-1">
              <FieldRenderer
                fieldPath={fieldPath}
                schema={schema}
                value={value}
                onChange={onChange}
                error={fieldError}
                context={context}
              />
              <span className="block text-[10px] text-ink/30">
                Multiple values supported (nargs={String(schema.nargs)})
              </span>
            </div>
          );
        }

        return (
          <FieldRenderer
            key={fieldPath}
            fieldPath={fieldPath}
            schema={schema}
            value={value}
            onChange={onChange}
            error={fieldError}
            context={context}
          />
        );
      })}

      {/* Retry button */}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="w-full py-1.5 text-xs text-accent hover:text-accent/80 border border-dashed border-line rounded transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}

// ── Loading Skeleton ──────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <SkeletonBlock lines={1} />
      <SkeletonBlock lines={2} />
      <SkeletonBlock lines={1} />
      <SkeletonBlock lines={3} />
    </div>
  );
}

function SkeletonBlock({ lines }: { lines: number }) {
  return (
    <div className="space-y-2">
      <div className="h-3 w-28 bg-line rounded" />
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "h-8 bg-line rounded",
            i === lines - 1 ? "w-3/4" : "w-full",
          )}
        />
      ))}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────

/**
 * Retrieves a value from a nested object using a dotted path.
 * Returns `undefined` if any segment is missing.
 */
function getNestedValue(
  obj: Record<string, unknown>,
  dottedPath: string,
): unknown {
  return dottedPath.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object" && key in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[key];
    }
    return undefined;
  }, obj);
}
