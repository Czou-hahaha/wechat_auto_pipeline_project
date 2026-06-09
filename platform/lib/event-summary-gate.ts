import { normalizeEventTags } from "@/lib/event-tags";
import type { EventListItem } from "@/types/event";

/** 与 V3 event_mapper / EVENT_AI_PRESS_MIN_ARTICLES 对齐 */
export const MIN_ARTICLES_FOR_EVENT_PRESS = 2;
const MIN_PRESS_PREVIEW_CHARS = 50;

type ListLike = Pick<
  EventListItem,
  | "hasSummary"
  | "summaryKind"
  | "article_count"
  | "summaryPreview"
  | "qa_score"
>;

/**
 * 界面「已有摘要」= DeepSeek 事件通稿（event_press_zh）。
 * 兼容旧 BFF 误标 summaryKind=cluster 但已有通稿（qa_score>0）的情况。
 */
export function resolveHasSummary(item: ListLike): boolean {
  const articleCount = Number(item.article_count ?? 0);
  if (articleCount < MIN_ARTICLES_FOR_EVENT_PRESS) {
    return false;
  }

  const preview = (item.summaryPreview ?? "").trim();
  if (preview.length < MIN_PRESS_PREVIEW_CHARS) {
    return false;
  }

  const kind = (item.summaryKind ?? "").trim().toLowerCase();
  const qaScore = Number(item.qa_score ?? 0);

  if (kind === "press") {
    return true;
  }

  if (kind === "press_draft") {
    return false;
  }

  // 旧 BFF：有通稿时常误标 cluster；以 QA 分区分通稿 vs 仅簇摘要
  if (kind === "cluster" || kind === "") {
    return qaScore > 0;
  }

  if (kind === "none") {
    return false;
  }

  return Boolean(item.hasSummary) && qaScore > 0;
}

function shortNoSummaryReason(
  item: Pick<EventListItem, "noSummaryReason" | "article_count">,
): string | undefined {
  const raw = (item.noSummaryReason ?? "").trim();
  const n = Number(item.article_count ?? 0);
  if (n < MIN_ARTICLES_FOR_EVENT_PRESS) {
    return "稿数不足";
  }
  if (raw.includes("稿数不足") || raw.includes("参考稿不足")) {
    return "稿数不足";
  }
  return "待生成通稿";
}

export function normalizeEventListItem<T extends EventListItem>(item: T): T {
  const hasSummary = resolveHasSummary(item);
  return normalizeEventTags({
    ...item,
    hasSummary,
    summaryKind: hasSummary ? "press" : "none",
    summaryPreview: hasSummary ? item.summaryPreview : "",
    noSummaryReason: hasSummary ? undefined : shortNoSummaryReason(item),
  });
}

export function normalizeEventListItems(items: EventListItem[]): EventListItem[] {
  return items.map((e) => normalizeEventListItem(e));
}
