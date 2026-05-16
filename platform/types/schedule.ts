export interface ScheduleConfig {
  enabled: boolean;
  timezone: string;
  morning_hour: number;
  evening_hour: number;
  morning_time: string;
  evening_time: string;
  summary: string;
  env_path?: string;
  restart_hint?: string;
}
