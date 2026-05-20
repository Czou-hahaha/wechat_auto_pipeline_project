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
}

export interface QAReviewItem {
  eventId: string;
  title: string;
  qa: QADetail;
  rewrite_history: RewriteRound[];
  importance_score: number;
}
