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
