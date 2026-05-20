export type PipelineRunState = "idle" | "running" | "completed" | "failed";

export interface PipelineRunStats {
  candidates?: number;
  published?: number;
  failed?: number;
}

export interface PipelineRunStatus {
  state: PipelineRunState;
  message: string;
  startedAt: string;
  finishedAt: string;
  exitCode: number | null;
  pid: number | null;
  logTail: string;
  stats: PipelineRunStats;
}

export interface PipelineRunStartResponse {
  ok: boolean;
  error?: string;
  status: PipelineRunStatus;
}
