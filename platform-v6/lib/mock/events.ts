import type { DashboardData, EventIntelligence, EventListItem, QAReviewItem } from "@/types/event";

const BEIJING_PRESS = `3月27日，北京市十六届人大常委会第二十三次会议表决通过《北京市无人驾驶航空器管理规定》，该规定将于2026年5月1日起实施。规定对无人驾驶航空器的飞行、销售、运输、存储等环节作出全面规范，旨在平衡低空安全与产业发展需求。

根据规定，北京市行政区域全域被划定为无人驾驶航空器管制空域，所有室外飞行活动均需提出申请。市人大常委会法工委副主任熊菁华在新闻发布会上表示，国家空中交通管理机构已确定北京全域为管制空域，飞行活动须经批准。

在生产销售环节，规定明确禁止非法生产、组装、拼装、改装无人驾驶航空器或破解其系统；不得向北京市行政区域内的单位和个人销售、出租无人驾驶航空器及其核心部件。

存储环节，规定明确全市禁止新建无人驾驶航空器及其核心部件存储场所，禁止在六环路（含）以内设立存储场所。`;

const BEIJING_ID = "666eb4ad-9054-4ca8-8db6-8b800eadac9a";

const beijingArticles = [
  {
    id: "524a37f6-76b6-47e1-847b-84f74ddeab5e",
    title: "《北京市无人驾驶航空器管理规定》今年5月1日实施",
    url: "https://www.bjrd.gov.cn/rdzl/rdzc/fgjd/202604/t20260410_4579143.html",
    sourceHost: "bjrd.gov.cn",
    publishedAt: "2026-03-28T00:00:00+00:00",
    similarity: 0.92,
    excerpt: "市十六届人大常委会表决通过《北京市无人驾驶航空器管理规定》，自2026年5月1日起实施…",
  },
  {
    id: "9e8df553-06c1-40b1-befb-54768606c1af",
    title: "无人机神出鬼没 北京祭出最严新规禁飞禁售",
    url: "https://www.rfi.fr/cn/",
    sourceHost: "www.rfi.fr",
    publishedAt: "2026-04-29T00:00:00+00:00",
    similarity: 0.71,
    excerpt: "北京对无人驾驶航空器飞行、销售、运输、存储作出严格规范…",
  },
  {
    id: "dd61e3ad-69a1-48ec-89dd-5be8e2c40fc1",
    title: "@所有无人驾驶航空器爱好者，这份提示请收好",
    url: "https://www.beijing.gov.cn/",
    sourceHost: "www.beijing.gov.cn",
    publishedAt: "2026-04-27T00:00:00+00:00",
    similarity: 0.68,
    excerpt: "北京市无人驾驶航空器管理相关提示与合规要求…",
  },
];

function buildGrounding(press: string, articleIds: string[]) {
  return press.split("\n\n").filter(Boolean).map((text, i) => ({
    paragraphId: `p${i}`,
    text,
    articleIds: articleIds.slice(0, 2),
    confidence: 0.75 + (i % 3) * 0.07,
  }));
}

export const MOCK_EVENTS: EventIntelligence[] = [
  {
    id: BEIJING_ID,
    title: "《北京市无人驾驶航空器管理规定》今年5月1日实施",
    importance_score: 94,
    qa_score: 95,
    article_count: 4,
    summary: BEIJING_PRESS,
    summaryPreview: BEIJING_PRESS.slice(0, 200) + "…",
    keywords: ["无人机", "北京", "禁飞", "低空经济", "BVLOS"],
    countries: ["CN"],
    timeline: [
      {
        id: "tl-1",
        at: "2026-03-28T00:00:00+00:00",
        label: "人大网发布法规全文",
        type: "article",
        articleId: beijingArticles[0].id,
        sourceHost: "bjrd.gov.cn",
      },
      {
        id: "tl-2",
        at: "2026-05-16T14:55:19+00:00",
        label: "AI 通稿生成",
        type: "press",
      },
    ],
    articles: beijingArticles,
    sourceDomains: ["bjrd.gov.cn", "www.rfi.fr", "www.beijing.gov.cn"],
    rewrite_history: [
      {
        round: 0,
        at: "2026-05-16T14:55:19+00:00",
        before: "",
        after: BEIJING_PRESS,
        reason: "初稿（未触发重写）",
      },
    ],
    grounding: buildGrounding(
      BEIJING_PRESS,
      beijingArticles.map((a) => a.id),
    ),
    qa: {
      score: 95,
      approved: true,
      hallucinationRisk: "low",
      hallucination: false,
      rewriteTriggered: false,
      rewriteAttempts: 0,
      aiStyleRisk: 12,
      missingFacts: [],
      issues: [],
      rejectedArticleIds: [],
      stoppedReason: "passed_threshold",
    },
    createdAt: "2026-05-16T14:55:09+00:00",
  },
  {
    id: "evt-faa-bvlos-001",
    title: "FAA 扩大 BVLOS 无人机运营试点范围",
    importance_score: 88,
    qa_score: 82,
    article_count: 6,
    summary:
      "美国联邦航空管理局（FAA）宣布扩大超视距（BVLOS）商业无人机运营试点，涵盖物流巡检与基础设施监测场景。多家 eVTOL 运营商提交合规方案，预计 Q3 进入规模化验证阶段。",
    summaryPreview:
      "FAA 扩大 BVLOS 商业无人机运营试点，eVTOL 运营商提交合规方案…",
    keywords: ["FAA", "BVLOS", "eVTOL", "无人机"],
    countries: ["INTL"],
    timeline: [
      {
        id: "tl-faa-1",
        at: "2026-05-14T10:00:00+00:00",
        label: "FAA 发布试点扩展通告",
        type: "article",
        sourceHost: "faa.gov",
      },
    ],
    articles: [
      {
        id: "a-faa-1",
        title: "FAA Expands BVLOS Drone Operations",
        url: "https://www.faa.gov/",
        sourceHost: "faa.gov",
        publishedAt: "2026-05-14T10:00:00+00:00",
        similarity: 0.89,
        excerpt: "The FAA announced expanded beyond visual line of sight operations…",
      },
    ],
    sourceDomains: ["faa.gov"],
    rewrite_history: [
      {
        round: 1,
        at: "2026-05-15T08:00:00+00:00",
        before: "FAA 扩大试点【初稿占位】",
        after: "FAA 扩大 BVLOS 无人机运营试点范围【终稿】",
        reason: "QA：缺少具体场景描述",
      },
    ],
    grounding: buildGrounding(
      "FAA 扩大 BVLOS 试点。eVTOL 运营商提交方案。",
      ["a-faa-1"],
    ),
    qa: {
      score: 82,
      approved: true,
      hallucinationRisk: "low-medium",
      hallucination: false,
      rewriteTriggered: true,
      rewriteAttempts: 1,
      aiStyleRisk: 28,
      missingFacts: ["具体试点城市名单"],
      issues: [
        {
          type: "completeness",
          severity: "medium",
          description: "未列出首批试点运营主体",
        },
      ],
      rejectedArticleIds: [],
    },
    createdAt: "2026-05-14T12:00:00+00:00",
  },
  {
    id: "evt-evtOL-sz-002",
    title: "深圳低空经济示范区 eVTOL 航线获批",
    importance_score: 91,
    qa_score: 88,
    article_count: 5,
    summary:
      "深圳市低空经济示范区获批多条 eVTOL 短途客运航线，连接宝安机场与前海、坂田片区。政策明确空域协调机制与起降场建设标准，被视为国内城市空中交通的重要里程碑。",
    summaryPreview: "深圳获批 eVTOL 短途客运航线，连接宝安与前海…",
    keywords: ["eVTOL", "低空经济", "深圳", "UAM"],
    countries: ["CN"],
    timeline: [],
    articles: [
      {
        id: "a-sz-1",
        title: "深圳 eVTOL 航线获批",
        url: "https://www.sz.gov.cn/",
        sourceHost: "sz.gov.cn",
        publishedAt: "2026-05-13T00:00:00+00:00",
        similarity: 0.85,
        excerpt: "多条 eVTOL 短途客运航线进入审批落地阶段…",
      },
    ],
    rewrite_history: [
      {
        round: 0,
        at: "2026-05-13T18:00:00+00:00",
        before: "",
        after: "深圳 eVTOL 航线获批…",
        reason: "初稿",
      },
    ],
    grounding: buildGrounding("深圳 eVTOL 航线获批。", ["a-sz-1"]),
    qa: {
      score: 88,
      approved: true,
      hallucinationRisk: "low",
      hallucination: false,
      rewriteTriggered: false,
      rewriteAttempts: 0,
      aiStyleRisk: 15,
      missingFacts: [],
      issues: [],
      rejectedArticleIds: [],
    },
    createdAt: "2026-05-13T18:00:00+00:00",
  },
  {
    id: "evt-uam-eu-003",
    title: "欧盟 UAM 框架下跨城无人机物流互通试点",
    importance_score: 76,
    qa_score: 71,
    article_count: 3,
    summary:
      "欧盟在 UAM 统一框架下启动跨城无人机物流互通试点，重点验证跨境 BVLOS 调度与应急备降协议。部分成员国对数据出境提出附加条件。",
    summaryPreview: "欧盟启动跨境无人机物流 BVLOS 试点…",
    keywords: ["UAM", "BVLOS", "无人机", "欧盟"],
    countries: ["INTL"],
    timeline: [],
    articles: [
      {
        id: "a-eu-1",
        title: "EU cross-border drone logistics pilot",
        url: "https://ec.europa.eu/",
        sourceHost: "ec.europa.eu",
        publishedAt: "2026-05-12T00:00:00+00:00",
        similarity: 0.77,
        excerpt: "Cross-border BVLOS logistics pilot under UAM framework…",
      },
    ],
    rewrite_history: [
      {
        round: 1,
        at: "2026-05-12T20:00:00+00:00",
        before: "欧盟试点启动【简略】",
        after: "欧盟 UAM 框架下跨城无人机物流互通试点【补充数据出境条款】",
        reason: "QA：幻觉风险 — 未核实数据条款",
      },
    ],
    grounding: buildGrounding("欧盟跨境 BVLOS 试点。", ["a-eu-1"]),
    qa: {
      score: 71,
      approved: false,
      hallucinationRisk: "medium",
      hallucination: false,
      rewriteTriggered: true,
      rewriteAttempts: 1,
      aiStyleRisk: 35,
      missingFacts: ["试点参与城市数量"],
      issues: [
        {
          type: "verification",
          severity: "high",
          description: "数据出境条款需对照原文",
        },
      ],
      rejectedArticleIds: [],
    },
    createdAt: "2026-05-12T20:00:00+00:00",
  },
];

function mockHasEventPress(e: EventIntelligence): boolean {
  const press = (e.summary || "").trim();
  if (press.length < 150) return false;
  if ((e.article_count ?? 0) < 2) return false;
  const hasPressStep = (e.timeline ?? []).some((t) => t.type === "press");
  const qaOk = Boolean(e.qa?.approved);
  return hasPressStep && qaOk;
}

export function mockEventList(): EventListItem[] {
  return MOCK_EVENTS.map((e) => {
    const press = (e.summary || "").trim();
    const hasSummary = mockHasEventPress(e);
    const pushed = Boolean(e.wechatDraftPushedAt?.trim());
    const tags = pushed
      ? (["草稿已推"] as const)
      : hasSummary
        ? (["可推送"] as const)
        : (e.article_count ?? 0) >= 1 && (e.expansion_article_count ?? 0) === 0
          ? (["待扩搜"] as const)
          : ([] as const);
    return {
      id: e.id,
      title: e.title,
      hasSummary,
      tags: [...tags],
      pushable: tags.includes("可推送"),
      pushed: tags.includes("草稿已推"),
      needsExpansion: tags.includes("待扩搜"),
      summaryKind: hasSummary ? "press" : "none",
      seed_article_count: e.seed_article_count,
      expansion_article_count: e.expansion_article_count,
      titleZh: hasSummary ? undefined : "低空经济政策动态（示意译文）",
      noSummaryReason: hasSummary ? undefined : "未生成新闻稿（Mock）",
      summaryPreview: hasSummary ? press.slice(0, 220) : "",
      wechatDraftPushedAt: e.wechatDraftPushedAt,
      importance_score: e.importance_score,
      qa_score: e.qa_score,
      article_count: e.article_count,
      keywords: e.keywords,
      countries: e.countries,
      timeline: e.timeline.slice(-3),
      createdAt: e.createdAt,
    };
  }).sort((a, b) => b.importance_score - a.importance_score);
}

export function mockEventById(id: string): EventIntelligence | null {
  return MOCK_EVENTS.find((e) => e.id === id) ?? null;
}

export function mockDashboard(): DashboardData {
  const list = mockEventList();
  return {
    todayNewEvents: 2,
    highImportanceEvents: list.slice(0, 5),
    hotKeywords: [
      { keyword: "eVTOL", count: 12 },
      { keyword: "BVLOS", count: 9 },
      { keyword: "低空经济", count: 8 },
      { keyword: "FAA", count: 7 },
      { keyword: "无人机", count: 15 },
    ],
    regionSplit: { domestic: 2, international: 2 },
    topicTrend: [
      { date: "05-10", FAA: 12, BVLOS: 8, eVTOL: 15 },
      { date: "05-11", FAA: 14, BVLOS: 9, eVTOL: 18 },
      { date: "05-12", FAA: 13, BVLOS: 11, eVTOL: 20 },
      { date: "05-13", FAA: 16, BVLOS: 12, eVTOL: 22 },
      { date: "05-14", FAA: 18, BVLOS: 14, eVTOL: 25 },
      { date: "05-15", FAA: 17, BVLOS: 15, eVTOL: 28 },
      { date: "05-16", FAA: 20, BVLOS: 16, eVTOL: 30 },
    ],
    aiRewriteCount: 3,
    avgQaScore: 84,
    totalEvents: MOCK_EVENTS.length,
  };
}

export function mockQAReviews(): QAReviewItem[] {
  return MOCK_EVENTS.filter((e) => e.summary).map((e) => ({
    eventId: e.id,
    title: e.title,
    qa: e.qa,
    rewrite_history: e.rewrite_history,
    importance_score: e.importance_score,
  }));
}

export function mockSearch(q: string, mode: string) {
  const needle = q.toLowerCase();
  let items = mockEventList();
  if (needle) {
    items = items.filter(
      (e) =>
        e.title.toLowerCase().includes(needle) ||
        e.keywords.some((k) => k.toLowerCase().includes(needle)) ||
        e.summaryPreview.toLowerCase().includes(needle),
    );
  }
  return { items, total: items.length, mode: "unified" };
}
