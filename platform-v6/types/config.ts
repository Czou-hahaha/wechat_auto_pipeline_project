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

export interface NotificationItem {
  id: string;
  kind: string;
  level: string;
  title: string;
  message: string;
  sourceId?: string;
  probeUrl?: string;
  createdAt?: string;
  action?: string;
}

export interface NotificationsPayload {
  items: NotificationItem[];
  total: number;
  healthSummary?: {
    lastScanAt?: string;
    alertCount?: number;
    unacknowledgedCount?: number;
  };
}

export interface SourceIntakeProbeResult {
  recommendedMode?: "rss" | "html_list" | "browser_zh" | string;
  domain?: string;
  probes?: Record<string, { ok?: boolean; sampleCount?: number; error?: string }>;
  draftSource?: DataSourceRecord;
  draftBrowserZh?: Record<string, unknown>;
  missingFields?: string[];
}

export interface FeedbackPromptSuggestion {
  id: string;
  created_at: string;
  window_days: number;
  reasons: string[];
  diff?: {
    hard_rules?: { add?: string[] };
    soft_rules?: { add?: string[] };
  };
  proposed_contract?: {
    hard_rules?: string[];
    soft_rules?: string[];
  };
  requires_manual_confirm_token?: string;
}

export interface FeedbackSummaryWithPrompt {
  total: number;
  byStage: Record<string, number>;
  byCategory: Record<string, number>;
  latest: { eventId?: string; category?: string; note?: string; createdAt?: string }[];
  promptSuggestion?: FeedbackPromptSuggestion | null;
  policyRecommendation?: FeedbackPolicyRecommendation | null;
}

export function ingestModeBadge(mode?: string): { label: string; className: string } {
  if (mode === "rss") {
    return { label: "RSS", className: "border-sky-500/30 bg-sky-500/10 text-sky-700" };
  }
  if (mode === "browser_zh") {
    return { label: "搜索", className: "border-violet-500/30 bg-violet-500/10 text-violet-700" };
  }
  return { label: "栏目", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700" };
}
