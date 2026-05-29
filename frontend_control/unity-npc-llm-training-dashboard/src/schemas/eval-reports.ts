import { z } from 'zod';

export const EvalReportFileSchema = z.object({
  name: z.string(),
  path: z.string(),
});

export const EvalReportGroupSchema = z.object({
  npcKey: z.string(),
  files: z.array(EvalReportFileSchema),
});

export const EvalReportsDataSchema = z.object({
  reports: z.array(EvalReportGroupSchema),
  comparisons: z.array(EvalReportFileSchema),
});

export type ValidatedEvalReportsData = z.infer<typeof EvalReportsDataSchema>;
export type EvalReportFile = z.infer<typeof EvalReportFileSchema>;
