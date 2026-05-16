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
  national_policy?: string[];
  local_policy?: string[];
  intl_coopcomp?: string[];
  frontier_tech?: string[];
  site_core_keywords?: string[];
  professional_site_keywords?: string[];
  [key: string]: string[] | undefined;
}

export const KEYWORD_SECTIONS: { key: string; label: string; hint: string }[] = [
  { key: "chinese_keywords", label: "中文检索词", hint: "GDELT / 主题检索主用词" },
  { key: "english_keywords", label: "英文检索词", hint: "国际源与英文 GDELT" },
  { key: "site_core_keywords", label: "站点核心词", hint: "专业站点 phase1 泛化词" },
  { key: "national_policy", label: "国家政策", hint: "分类检索（可选）" },
  { key: "local_policy", label: "地方政策", hint: "分类检索（可选）" },
  { key: "intl_coopcomp", label: "国际合作/竞争", hint: "分类检索（可选）" },
  { key: "frontier_tech", label: "前沿技术", hint: "分类检索（可选）" },
];
