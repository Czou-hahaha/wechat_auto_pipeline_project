export type DataSourceHealthStatus =
  | "ok"
  | "failed"
  | "checking"
  | "unknown";

export interface DataSourceHealthEntry {
  key: string;
  source_id?: string;
  name?: string;
  status: DataSourceHealthStatus;
  message?: string;
  checked_at?: string;
  sample_count?: number;
  needs_attention?: boolean;
  probe_url?: string;
}

export interface DataSourceHealthAlert {
  key: string;
  source_id?: string;
  name?: string;
  message?: string;
  checked_at?: string;
  probe_url?: string;
}

export interface DataSourceHealthResponse {
  sources: Record<string, DataSourceHealthEntry>;
  alerts: DataSourceHealthAlert[];
  last_full_scan_at?: string;
  summary?: {
    total: number;
    ok: number;
    failed: number;
    needs_attention: number;
  };
}

export interface DataSourceRecord {
  id: string;
  name: string;
  kind: string;
  source_type?: string;
  region?: string;
  language?: string;
  value: string;
  ingest_mode?: string;
  list_monitor_url?: string;
  rss?: string;
  rss_available?: boolean;
  importance_score?: number;
  tags?: string[];
}

export interface SourceCandidateRecord {
  host: string;
  mention_count: number;
  status: "new" | "ready" | "blocked" | string;
  ingest_mode?: string;
  probe_url?: string;
  last_probe_status?: string;
  last_probe_message?: string;
  last_probe_sample_count?: number;
  last_probed_at?: string;
  last_seen_at?: string;
}

export interface FeedbackPolicyRecommendation {
  id: string;
  created_at: string;
  window_days: number;
  feedback_total: number;
  by_category: Record<string, number>;
  proposed_overrides: Record<string, unknown>;
  reasons: string[];
  safe_to_apply: boolean;
  safety_notes: string[];
  requires_manual_confirm_token?: string;
}

export interface PromptContractPayload {
  contract: {
    objective: string;
    hard_rules: string[];
    soft_rules?: string[];
    enforcement?: {
      hard?: string;
      soft?: string;
    };
    effective_runtime: Record<string, unknown>;
    policy_overrides: Record<string, unknown>;
  };
}

export interface PromptPreviewPayload {
  version: string;
  systemPreview: string;
  userTemplatePreview: string;
}

/** 与后端 source_health_key 一致 */
export function sourceHealthKey(row: DataSourceRecord): string {
  const sid = (row.id || "").trim();
  const mode = (row.ingest_mode || "html_list").toLowerCase();
  const url =
    mode === "rss" || row.rss_available
      ? (row.rss || row.list_monitor_url || "").trim()
      : (row.list_monitor_url || "").trim();
  return url ? `${sid}|${url}` : sid;
}

export interface KeywordsConfig {
  english_keywords?: string[];
  chinese_keywords?: string[];
}

export const KEYWORD_SECTIONS: { key: keyof KeywordsConfig; label: string }[] = [
  { key: "chinese_keywords", label: "中文检索词" },
  { key: "english_keywords", label: "英文检索词" },
];

export function languageLabel(lang?: string): string {
  const l = (lang || "zh").toLowerCase();
  if (l === "en" || l === "english") return "英文";
  return "中文";
}
