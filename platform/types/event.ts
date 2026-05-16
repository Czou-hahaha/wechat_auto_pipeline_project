export interface TimelineNode {
  id: string;
  at: string;
  label: string;
  type: "article" | "cluster" | "press";
  articleId?: string;
  sourceHost?: string;
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
}

export interface GroundingSpan {
  paragraphId: string;
  text: string;
  articleIds: string[];
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
}

export interface EventListItem {
  id: string;
  title: string;
  importance_score: number;
  qa_score: number;
  article_count: number;
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
  topicTrend: { date: string; FAA: number; BVLOS: number; eVTOL: number }[];
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
