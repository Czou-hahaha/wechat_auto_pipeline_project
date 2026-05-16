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
  morning_hour: 8,
  evening_hour: 20,
  morning_time: "08:00",
  evening_time: "20:00",
  summary: "每日 08:00、20:00（Asia/Shanghai）各执行一次 run-once",
  restart_hint: "修改后需重启 run-scheduler 进程后生效",
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
  national_policy: ["低空经济 政策"],
  local_policy: ["低空经济 地方"],
  intl_coopcomp: ["无人机 国际"],
  frontier_tech: ["eVTOL 技术"],
  site_core_keywords: ["无人机", "低空经济"],
};
