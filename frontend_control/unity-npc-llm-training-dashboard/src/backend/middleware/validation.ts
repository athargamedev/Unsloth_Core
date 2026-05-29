import type { Request, Response, NextFunction } from "express";
import { z } from "zod";

/**
 * Middleware factory that validates `req.body` against a Zod schema.
 * Returns 400 with error details if validation fails.
 */
export function validate<T>(schema: z.ZodType<T>) {
  return (req: Request, res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      const errors = result.error.issues.map((issue) => ({
        path: issue.path.join("."),
        message: issue.message,
      }));
      res.status(400).json({ error: "Validation failed", details: errors });
      return;
    }
    req.body = result.data;
    next();
  };
}

// ── Common schemas ────────────────────────────────────────────────────────

const knownCommands = [
  'validate-spec', 'dataset-generate', 'generate-ollama', 'dataset-sanitize',
  'dataset-eval', 'training', 'export', 'evaluate', 'feedback',
  'quick-eval', 'batch-export', 'validate-config',
] as const;

export const startCommandSchema = z.object({
  commandId: z.enum(knownCommands as unknown as [string, ...string[]], {
    error: `commandId must be one of: ${knownCommands.join(', ')}`,
  }),
  spec: z.string().optional(),
  preset: z.string().optional(),
  npcKey: z.string().optional(),
  type: z.string().optional(),
  options: z.record(z.string(), z.unknown()).optional(),
});

export const stopJobSchema = z.object({
  id: z.string().min(1, "id is required").regex(/^[a-zA-Z0-9_-]+$/, "Invalid job id format"),
});

export const createWorkflowSchema = z.object({
  spec: z.string().min(1, "spec is required"),
  preset: z.string().optional(),
  technique: z.enum(['template', 'docs', 'ollama', 'openai', 'anthropic']).optional(),
  options: z.record(z.string(), z.unknown()).optional(),
});
