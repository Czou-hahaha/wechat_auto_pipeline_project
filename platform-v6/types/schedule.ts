export interface ScheduleJob {
  id: string;
  label: string;
  hour: number;
  minute: number;
}

export interface ArticleAgeConfig {
  unit: "hours" | "days";
  value: number;
}

export interface SchedulerRunStatus {
  state: "running" | "stopped" | string;
  message: string;
  startedAt?: string;
  pid?: number | null;
  jobsSummary?: string;
}

export interface ScheduleConfig {
  enabled: boolean;
  timezone: string;
  jobs: ScheduleJob[];
  article_age: ArticleAgeConfig;
  /** 关闭后不写入时间窗过滤（MAX_ARTICLE_AGE_HOURS=0） */
  article_age_limit_enabled?: boolean;
  /** 写入 .env 的小时数（由天/小时换算）；未限制时为 0 */
  article_age_hours: number;
  summary: string;
  scheduler?: SchedulerRunStatus;
  schedulerNote?: string;
  schedulerWarning?: string;
}

export function newScheduleJob(): ScheduleJob {
  return {
    id: `job_${Date.now()}`,
    label: "新定时任务",
    hour: 9,
    minute: 0,
  };
}
