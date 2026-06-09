"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { EventListRow } from "@/features/events/event-list-row";
import {
  tabActiveDraft,
  tabActiveExpand,
  tabActiveReady,
  tabInactive,
  textCaption,
  textMetaSm,
  textPageDesc,
} from "@/lib/content-text";
import {
  EVENT_LIST_PAGE_SIZE,
  eventMatchesSegment,
  resolveEventSegment,
  SEGMENT_HINTS,
  type EventListSegment,
} from "@/lib/event-tags";
import { cn } from "@/lib/utils";
import type { EventListItem } from "@/types/event";

const SEGMENTS: EventListSegment[] = ["可推送", "草稿已推", "待扩搜"];

function sortByRecentDesc(items: EventListItem[]): EventListItem[] {
  return [...items].sort((a, b) =>
    (b.createdAt || "").localeCompare(a.createdAt || ""),
  );
}

const SEGMENT_PARAM = "segment";

export function EventsPaginatedList({ items }: { items: EventListItem[] }) {
  const searchParams = useSearchParams();
  const initialSegment = ((): EventListSegment => {
    const q = searchParams.get(SEGMENT_PARAM);
    if (q === "可推送" || q === "草稿已推" || q === "待扩搜") return q;
    return "可推送";
  })();
  const [segment, setSegment] = useState<EventListSegment>(initialSegment);
  const [page, setPage] = useState(1);

  const counts = useMemo(() => {
    const out: Record<EventListSegment, number> = {
      可推送: 0,
      草稿已推: 0,
      待扩搜: 0,
    };
    for (const ev of items) {
      const seg = resolveEventSegment(ev);
      if (seg) out[seg] += 1;
    }
    return out;
  }, [items]);

  const filtered = useMemo(() => {
    const sorted = sortByRecentDesc(items);
    return sorted.filter((ev) => eventMatchesSegment(ev, segment));
  }, [items, segment]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / EVENT_LIST_PAGE_SIZE));

  useEffect(() => {
    setPage(1);
  }, [segment, items.length]);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  useEffect(() => {
    if (counts[segment] === 0) {
      const fallback = SEGMENTS.find((s) => counts[s] > 0);
      if (fallback && fallback !== segment) setSegment(fallback);
    }
  }, [counts, segment]);

  const pageItems = filtered.slice(
    (page - 1) * EVENT_LIST_PAGE_SIZE,
    page * EVENT_LIST_PAGE_SIZE,
  );

  function activeTabClass(key: EventListSegment) {
    if (key === "草稿已推") return tabActiveDraft;
    if (key === "可推送") return tabActiveReady;
    return tabActiveExpand;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {SEGMENTS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setSegment(key)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
              segment === key ? activeTabClass(key) : tabInactive,
            )}
          >
            {key}
            <span className="ml-1.5 tabular-nums opacity-80">{counts[key]}</span>
          </button>
        ))}
      </div>
      <p className={`leading-relaxed ${textMetaSm}`}>
        {SEGMENT_HINTS[segment]}
        <span className="text-zinc-700">
          {" "}
          · 本系统不接入群发/发表状态，无法判断文章是否已在公众号上线。
        </span>
      </p>

      {pageItems.length ? (
        <div className="glass overflow-hidden rounded-lg border border-zinc-200">
          {pageItems.map((ev) => (
            <EventListRow key={ev.id} event={ev} />
          ))}
        </div>
      ) : (
        <p className={`py-8 text-center ${textPageDesc}`}>
          {segment === "草稿已推" ? (
            <>
              暂无记录。须在事件详情点击「推送草稿箱」或「标记草稿已推」后才会出现在此；
              <br />
              仅在微信后台手工推草稿、未点标记时，本系统无法自动识别。
            </>
          ) : (
            <>「{segment}」暂无事件</>
          )}
        </p>
      )}

      {filtered.length > EVENT_LIST_PAGE_SIZE ? (
        <div className={`flex flex-wrap items-center justify-between gap-2 ${textCaption}`}>
          <span>
            第 {page} / {totalPages} 页 · 共 {filtered.length} 条
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-md border border-zinc-200 px-2.5 py-1 text-zinc-600 hover:text-zinc-900 disabled:opacity-40"
            >
              上一页
            </button>
            <button
              type="button"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="rounded-md border border-zinc-200 px-2.5 py-1 text-zinc-600 hover:text-zinc-900 disabled:opacity-40"
            >
              下一页
            </button>
          </div>
        </div>
      ) : filtered.length > 0 ? (
        <p className={textCaption}>共 {filtered.length} 条</p>
      ) : null}
    </div>
  );
}
