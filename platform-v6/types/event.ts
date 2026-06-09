export interface TimelineNode {
  id: string;
  at: string;
  label: string;
  type: "article" | "cluster" | "press" | "enhancement" | "expansion";
  articleId?: string;
  sourceHost?: string;
  sourceKind?: "seed" | "expansion" | "cluster" | "";
}

export interface SourceArticle {
  id: string;
  title: string;
  url: string;
  sourceHost: string;
  publishedAt: string;
  similarity: number;
  excerpt: string;
  rejected?: boolean;
  sourceKind?: "seed" | "expansion" | "cluster";
  status?: string;
  mapRole?: string;
}

export interface EnhancementSourceTrace {
  source: string;
  query: string;
  attempts: number;
  hits: number;
}

export interface EnhancementExpandedUrl {
  url: string;
  title: string;
  similarity: number;
}

export interface EventEnhancement {
  /** zh | en — 扩搜语言路由 */
  eventLang?: string;
  /** 中文 event 为 true，不调用 GDELT */
  gdeltSkipped?: boolean;
  searchCascade?: string[];
  ran: boolean;
  status: string;
  ranAt: string;
  seedArticleCount: number;
  articlesInserted: number;
  candidatesFetched: number;
  similarityThreshold: number;
  queries: string[];
  sourceTrace: EnhancementSourceTrace[];
  skippedReason?: string;
  expandedArticles: EnhancementExpandedUrl[];
}

export interface GroundingSpan {
  paragraphId: string;
  text: string;
  articleIds: string[];
  /** 服务端按段落匹配的参考稿（可直接展示链接） */
  sources?: SourceArticle[];
  confidence: number;
}

export interface RewriteRound {
  round: number;
  at: string;
  before: string;
  after: string;
  reason: string;
}

export interface QADetail {
  score: number;
  approved: boolean;
  hallucinationRisk: string;
  hallucination: boolean;
  rewriteTriggered: boolean;
  rewriteAttempts: number;
  aiStyleRisk: number;
  missingFacts: string[];
  issues: { type: string; severity: string; description: string }[];
  rejectedArticleIds: string[];
  stoppedReason?: string;
}

export interface EventMapNode {
  id: string;
  type: "event" | "article" | "entity" | string;
  label: string;
  host?: string;
  url?: string;
  eventId?: string | null;
  isCurrent?: boolean;
}

export interface EventMapEdge {
  source: string;
  target: string;
  relation: "supports" | "mentions" | string;
}

export interface EventMapEvidence {
  sourceHost: string;
  articleTitle: string;
  url: string;
  snippet: string;
}

export interface EventMapPayload {
  eventId: string;
  title: string;
  nodeCount: number;
  edgeCount: number;
  sourceDiversity: number;
  topSources: { host: string; count: number }[];
  nodes: EventMapNode[];
  edges: EventMapEdge[];
  evidence: EventMapEvidence[];
}

export interface EventMemorySnapshot {
  event_id: string;
  title: string;
  dominant_topic_key: string;
  qa_score: number;
  qa_stopped_reason: string;
  facts: {
    title: string;
    source_url: string;
    source_published_at: string;
  }[];
  updated_at: string;
}

export interface EventHistoryNode {
  eventId: string;
  title: string;
  createdAt: string;
  relation: "current" | "same_topic" | "semantic_neighbor" | string;
  score: number;
}

export interface EventHistoryPayload {
  eventId: string;
  currentTitle: string;
  chain: EventHistoryNode[];
  timelineReport: string;
}

export interface EventIntelligence {
  id: string;
  title: string;
  importance_score: number;
  qa_score: number;
  article_count: number;
  summary: string;
  summaryPreview?: string;
  keywords: string[];
  countries: string[];
  timeline: TimelineNode[];
  articles: SourceArticle[];
  sourceDomains?: string[];
  rewrite_history: RewriteRound[];
  grounding: GroundingSpan[];
  qa: QADetail;
  createdAt?: string;
  dominantTopicKey?: string;
  seed_article_count?: number;
  expansion_article_count?: number;
  enhancement?: EventEnhancement;
  wechatDraftPushedAt?: string;
}

export interface EventListItem {
  id: string;
  title: string;
  /** 外文原标题（与 title 不同时展示） */
  titleOriginal?: string;
  /** 无摘要事件的中文标题（展示在卡片下方） */
  titleZh?: string;
  /** 是否已有 QA 通过的 DeepSeek 通稿 */
  hasSummary: boolean;
  /** 工作流分段（互斥）；草稿已推 ≠ 公众号已发表 */
  tags?: ("可推送" | "草稿已推" | "待扩搜")[];
  pushable?: boolean;
  pushed?: boolean;
  needsExpansion?: boolean;
  /** press=已有通稿 | none */
  summaryKind?: "press" | "none";
  noSummaryReason?: string;
  wechatDraftPushedAt?: string;
  importance_score: number;
  qa_score: number;
  article_count: number;
  seed_article_count?: number;
  expansion_article_count?: number;
  enhancement_status?: string;
  enhancement_inserted?: number;
  summaryPreview: string;
  keywords: string[];
  countries: string[];
  timeline: TimelineNode[];
  createdAt?: string;
}

export interface DashboardData {
  todayNewEvents: number;
  highImportanceEvents: EventListItem[];
  hotKeywords: { keyword: string; count: number }[];
  regionSplit: { domestic: number; international: number };
  topicTrend: Record<string, string | number>[];
  aiRewriteCount: number;
  avgQaScore: number;
  totalEvents: number;
  phaseTimings?: { total_sec?: number; phases?: Record<string, number> };
  notificationCount?: number;
}

export interface EventGraphTimelineItem {
  date?: string;
  kind?: string;
  update?: string;
  source?: string;
}

export interface EventIntelligenceGraphPayload {
  eventId: string;
  title: string;
  map?: {
    nodeCount?: number;
    edgeCount?: number;
    sourceDiversity?: number;
    topSources?: { host: string; count: number }[];
    evidence?: EventMapEvidence[];
  };
  graph?: {
    graphEventId?: string | null;
    title?: string;
    summary?: string;
    evolutionKind?: string;
    timeline?: EventGraphTimelineItem[];
    nodes?: EventMapNode[];
    edges?: EventMapEdge[];
  };
  history?: EventHistoryPayload;
  memory?: {
    title?: string;
    dominantTopicKey?: string;
    qaScore?: number;
    qaStoppedReason?: string;
    facts?: { title: string; source_url?: string }[];
    updatedAt?: string;
  };
  visualization?: {
    nodes?: EventMapNode[];
    edges?: EventMapEdge[];
  };
  eventGraph?: {
    nodes?: EventMapNode[];
    edges?: EventMapEdge[];
  };
}

export interface QAReviewItem {
  eventId: string;
  title: string;
  qa: QADetail;
  rewrite_history: RewriteRound[];
  importance_score: number;
}
