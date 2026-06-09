import {
  MIN_ARTICLES_FOR_EVENT_PRESS,
  resolveHasSummary,
} from "@/lib/event-summary-gate";
import type { EventListItem } from "@/types/event";

export const EVENT_LIST_PAGE_SIZE = 10;

/**
 * 列表分段顺序：可推送 → 草稿已推 → 待扩搜
 * 「草稿已推」= 已写入微信公众号草稿箱（event_wechat_draft_pushed_at），
 * 不代表已在后台群发/发表上线。
 */
export type EventListSegment = "可推送" | "草稿已推" | "待扩搜";

export const SEGMENT_HINTS: Record<EventListSegment, string> = {
  可推送: "通稿已就绪，可写入公众号草稿箱",
  草稿已推: "已写入草稿箱；是否发表需在公众平台自行核对",
  待扩搜: "有主稿、待扩搜参考稿后再生成通稿",
};

const MIN_QA_FOR_PUSH = 70;

type TagInput = Pick<
  EventListItem,
  | "tags"
  | "pushable"
  | "pushed"
  | "needsExpansion"
  | "hasSummary"
  | "summaryKind"
  | "summaryPreview"
  | "qa_score"
  | "article_count"
  | "seed_article_count"
  | "expansion_article_count"
  | "wechatDraftPushedAt"
>;

export function resolvePushed(item: TagInput): boolean {
  if (typeof item.pushed === "boolean") return item.pushed;
  if (Boolean(item.wechatDraftPushedAt?.trim())) return true;
  return (item.tags ?? []).includes("草稿已推");
}

function referenceCount(item: TagInput): number {
  const seed = Number(item.seed_article_count ?? 0);
  if (seed > 0) return seed;
  const total = Number(item.article_count ?? 0);
  const exp = Number(item.expansion_article_count ?? 0);
  return Math.max(0, total - exp);
}

export function resolvePushable(item: TagInput): boolean {
  if (resolvePushed(item)) return false;
  if (typeof item.pushable === "boolean") return item.pushable;
  if (!resolveHasSummary(item)) return false;
  return Number(item.qa_score ?? 0) >= MIN_QA_FOR_PUSH;
}

export function resolveNeedsExpansion(item: TagInput): boolean {
  if (resolvePushed(item) || resolvePushable(item)) return false;
  if (Number(item.seed_article_count ?? 0) < 1) return false;
  if (typeof item.needsExpansion === "boolean") return item.needsExpansion;
  if (Number(item.expansion_article_count ?? 0) > 0) return false;
  return referenceCount(item) >= 1;
}

/** 每条事件归入唯一分段；以 wechatDraftPushedAt 为准，不盲信陈旧 tags。 */
export function resolveEventSegment(item: TagInput): EventListSegment | null {
  if (resolvePushed(item)) return "草稿已推";
  if (resolvePushable(item)) return "可推送";
  if (resolveNeedsExpansion(item)) return "待扩搜";
  const raw = (item.tags ?? [])[0];
  if (raw === "已推送") return "草稿已推";
  if (raw === "可推送" || raw === "草稿已推" || raw === "待扩搜") {
    return raw;
  }
  return null;
}

export function normalizeEventTags<T extends EventListItem>(item: T): T {
  const segment = resolveEventSegment(item);
  const tags = segment ? [segment] : [];
  return {
    ...item,
    tags,
    pushable: segment === "可推送",
    pushed: segment === "草稿已推",
    needsExpansion: segment === "待扩搜",
  };
}

export function eventMatchesSegment(
  item: EventListItem,
  segment: EventListSegment,
): boolean {
  return resolveEventSegment(item) === segment;
}

export function shortArticleMeta(item: EventListItem): string {
  const n = Number(item.article_count ?? 0);
  const exp = Number(item.expansion_article_count ?? 0);
  const seed = Number(item.seed_article_count ?? 0);
  const main = seed > 0 ? seed : Math.max(0, n - exp);
  const parts = [`${main} 主稿`];
  if (exp > 0) parts.push(`+${exp} 扩搜`);
  if (n < MIN_ARTICLES_FOR_EVENT_PRESS) parts.push("稿数不足");
  return parts.join(" · ");
}
