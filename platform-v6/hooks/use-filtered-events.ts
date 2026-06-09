"use client";

import { useDeferredValue, useMemo } from "react";
import { useEvents } from "@/hooks/use-events";
import { eventMatchesSegment, resolveEventSegment } from "@/lib/event-tags";
import type { EventListSegment } from "@/lib/event-tags";
import type { EventSort } from "@/store/event-filters";

/** 一次拉全量事件，重要性/搜索在本地过滤，避免滑块每次触发 BFF 重算。 */
export function useFilteredEvents(params: {
  q?: string;
  keyword?: string;
  minImportance?: number;
  sort?: EventSort;
}) {
  const deferredMin = useDeferredValue(params.minImportance ?? 0);
  const { data, isLoading, isFetching, error, refetch } = useEvents({
    q: params.q,
    keyword: params.keyword,
    sort: params.sort,
  });

  const items = useMemo(() => {
    let rows = data?.items ?? [];
    const needle = (params.q || params.keyword || "").trim().toLowerCase();
    if (needle) {
      rows = rows.filter(
        (e) =>
          e.title.toLowerCase().includes(needle) ||
          (e.titleZh || "").toLowerCase().includes(needle) ||
          e.keywords.some((k) => k.toLowerCase().includes(needle)),
      );
    }
    if (deferredMin > 0) {
      rows = rows.filter((e) => e.importance_score >= deferredMin);
    }
    const sort = params.sort ?? "recent";
    rows = [...rows];
    if (sort === "recent") {
      rows.sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || ""));
    } else if (sort === "qa") {
      rows.sort((a, b) => b.qa_score - a.qa_score);
    } else {
      rows.sort((a, b) => b.importance_score - a.importance_score);
    }
    return rows;
  }, [data?.items, deferredMin, params.q, params.keyword, params.sort]);

  return {
    items,
    total: items.length,
    isLoading,
    isFetching: isFetching || deferredMin !== (params.minImportance ?? 0),
    error,
    refetch,
  };
}

export function useSegmentCounts(items: ReturnType<typeof useFilteredEvents>["items"]) {
  return useMemo(() => {
    const counts: Record<EventListSegment, number> = {
      可推送: 0,
      草稿已推: 0,
      待扩搜: 0,
    };
    for (const ev of items) {
      const seg = resolveEventSegment(ev);
      if (seg) counts[seg] += 1;
    }
    return counts;
  }, [items]);
}

export function filterItemsBySegment(
  items: ReturnType<typeof useFilteredEvents>["items"],
  segment: EventListSegment,
) {
  return items.filter((ev) => eventMatchesSegment(ev, segment));
}
