import type { Express } from "express";
import express from "express";
import type { RouterDependencies } from "./types";
import { pathTraversalMiddleware, rateLimitMiddleware, jsonBodyParser } from "./middleware/security";
import { auditLog } from "./middleware/audit";
import { requireAuth } from "./middleware/auth";

// Route modules
import { registerRoutes as registerAuthRoutes } from "./routes/auth";
import { registerRoutes as registerJobsRoutes } from "./routes/jobs";
import { registerRoutes as registerPipelineRoutes } from "./routes/pipeline";
import { registerRoutes as registerDatasetsRoutes } from "./routes/datasets";
import { registerRoutes as registerEvalRoutes } from "./routes/eval";
import { registerRoutes as registerExportRoutes } from "./routes/export";
import { registerRoutes as registerTrainingRoutes } from "./routes/training";
import { registerRoutes as registerSystemRoutes } from "./routes/system";
import { registerRoutes as registerOllamaRoutes } from "./routes/ollama";
import { registerRoutes as registerSupabaseRoutes } from "./routes/supabase";
import { registerRoutes as registerCommandsRoutes } from "./routes/commands";
import { registerRoutes as registerWorkflowRoutes } from "./routes/workflow";

/**
 * Creates the Express application with all middleware and route modules mounted.
 *
 * @param deps - Shared dependencies (registry, broadcast, etc.)
 * @returns Configured Express app (not yet listening)
 */
export function createApp(deps: RouterDependencies): Express {
  const app = express();

  // ── Global Middleware (order matters) ────────────────────────────────────
  app.use(pathTraversalMiddleware);
  app.use(auditLog);
  app.use(requireAuth);
  app.use(jsonBodyParser);

  // Optional: apply rate limiting globally (commented out by default — enable in production)
  // app.use(rateLimitMiddleware(60_000, 100));

  // ── Route Registration ──────────────────────────────────────────────────
  registerAuthRoutes(app);
  registerJobsRoutes(app, deps);
  registerPipelineRoutes(app, deps);
  registerDatasetsRoutes(app, deps);
  registerEvalRoutes(app, deps);
  registerExportRoutes(app, deps);
  registerTrainingRoutes(app, deps);
  registerSystemRoutes(app, deps);
  registerOllamaRoutes(app, deps);
  registerSupabaseRoutes(app, deps);
  registerCommandsRoutes(app, deps);
  registerWorkflowRoutes(app, deps);

  return app;
}
