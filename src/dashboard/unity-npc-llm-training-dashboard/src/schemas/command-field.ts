// ── Shared Schema Types ───────────────────────────────────────────────────
// Copied from src/backend/types.ts so both frontend and backend import from
// the same source of truth.

export type FieldType = "string" | "number" | "boolean" | "path" | "array";
export type FlagType = "store" | "store_true" | "store_false" | "append" | "BooleanOptionalAction";
export type NargsValue = number | "+" | "*" | "?";

/**
 * Schema for a single CLI flag/field in a command.
 * Describes type, constraints, and UI rendering hints.
 */
export interface CommandFieldSchema {
  type: FieldType;
  required: boolean;
  /** Default value (number, string, boolean, or array for nargs) */
  default?: string | number | boolean | string[];
  /** Human-readable description */
  description?: string;
  /** Enum options (rendered as dropdown) */
  enum?: string[];
  /** For path types: "file" or "dir" */
  pathType?: "file" | "dir";
  /** For path types: acceptable project-relative root dirs for resolvePathWithinRoots */
  roots?: string[];
  /** argparse nargs: number, "+", "*", or "?" */
  nargs?: NargsValue;
  /** argparse action type */
  flagType?: FlagType;
  /** Display order in form (lower = first) */
  order?: number;
}
