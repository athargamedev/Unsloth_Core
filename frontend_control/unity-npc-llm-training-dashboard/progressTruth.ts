export type JobStatus = "pending" | "running" | "completed" | "failed" | "stopped";

export interface StageState {
  name: string;
  status: "completed" | "running" | "pending" | "failed" | "stopped";
  logs: string[];
}

export const deriveStageStatuses = (
  stages: StageState[],
  jobStatus: JobStatus,
  activeIndex: number,
  isPipelineJob: boolean,
): StageState[] => {
  return stages.map((stage, index) => {
    if (jobStatus === "completed") {
      if (isPipelineJob) return { ...stage, status: "completed" };
      return { ...stage, status: index <= activeIndex ? "completed" : "pending" };
    }

    if (jobStatus === "failed") {
      return { ...stage, status: index === activeIndex ? "failed" : index < activeIndex ? "completed" : "pending" };
    }

    if (jobStatus === "stopped") {
      return { ...stage, status: index === activeIndex ? "stopped" : index < activeIndex ? "completed" : "pending" };
    }

    if (jobStatus === "running" || jobStatus === "pending") {
      return { ...stage, status: index < activeIndex ? "completed" : index === activeIndex ? "running" : "pending" };
    }

    return stage;
  });
};

export const computeProgressFromStages = (
  jobStatus: JobStatus,
  stages: StageState[],
): number => {
  const totalStages = Math.max(stages.length, 1);

  if (jobStatus === "completed") return 100;

  const completedStages = stages.filter((stage) => stage.status === "completed").length;
  const runningStageIndex = stages.findIndex((stage) => stage.status === "running");
  const failedStageIndex = stages.findIndex((stage) => stage.status === "failed");
  const stoppedStageIndex = stages.findIndex((stage) => stage.status === "stopped");

  if (runningStageIndex >= 0) {
    const portion = ((runningStageIndex + 0.5) / totalStages) * 100;
    return Math.max(1, Math.min(99, Math.round(portion)));
  }

  if (failedStageIndex >= 0 || stoppedStageIndex >= 0) {
    const terminalIndex = failedStageIndex >= 0 ? failedStageIndex : stoppedStageIndex;
    const portion = ((terminalIndex + 0.5) / totalStages) * 100;
    return Math.max(1, Math.min(99, Math.round(portion)));
  }

  if (jobStatus === "pending") return 0;

  if (completedStages > 0) {
    const portion = (completedStages / totalStages) * 100;
    return Math.max(1, Math.min(99, Math.round(portion)));
  }

  return 0;
};
