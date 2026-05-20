/** 无 BFF 时的采集配置 mock（与 V3 config 结构一致） */

export const MOCK_DATA_SOURCES = [
  {
    id: "cn_gov_001",
    name: "中国政府网",
    kind: "web",
    source_type: "policy",
    region: "CN",
    language: "zh",
    value: "gov.cn",
    ingest_mode: "html_list",
    list_monitor_url: "https://www.gov.cn/zhengce/index.htm",
    importance_score: 100,
    tags: ["低空经济", "政策"],
  },
  {
    id: "cn_caac_001",
    name: "中国民航局",
    kind: "web",
    source_type: "aviation_policy",
    region: "CN",
    language: "zh",
    value: "caac.gov.cn",
    ingest_mode: "html_list",
    list_monitor_url: "https://www.caac.gov.cn/XXGK/XXGK/",
    importance_score: 95,
    tags: ["民航", "无人机"],
  },
];

export const MOCK_SCHEDULE = {
  enabled: false,
  timezone: "Asia/Shanghai",
  jobs: [
    { id: "job_morning", label: "早间采集", hour: 8, minute: 0 },
    { id: "job_evening", label: "晚间采集", hour: 20, minute: 0 },
  ],
  article_age: { unit: "hours" as const, value: 14 },
  article_age_limit_enabled: true,
  article_age_hours: 14,
  summary:
    "已配置 2 个定时点（08:00、20:00）；仅采集 近 14 小时 内发布的文章",
};

export const MOCK_KEYWORDS: Record<string, string[]> = {
  english_keywords: [
    "drone",
    "eVTOL",
    "BVLOS",
    "UAM",
  ],
  chinese_keywords: [
    "低空经济",
    "无人机",
    "飞行汽车",
  ],
};
