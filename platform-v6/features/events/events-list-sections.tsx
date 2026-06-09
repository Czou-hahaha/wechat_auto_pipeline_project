"use client";

import { useMemo } from "react";
import { EventListRow } from "@/features/events/event-list-row";
import { Badge } from "@/components/ui/badge";
import { resolveHasSummary } from "@/lib/event-summary-gate";
import type { EventListItem } from "@/types/event";

function sortByRecentDesc(items: EventListItem[]): EventListItem[] {
  return [...items].sort((a, b) =>
    (b.createdAt || "").localeCompare(a.createdAt || ""),
  );
}

function EventList({ items }: { items: EventListItem[] }) {
  if (!items.length) {
    return <p className="px-4 py-6 text-sm text-zinc-700">暂无事件</p>;
  }
  return (
    <div className="glass overflow-hidden rounded-xl border border-zinc-200">
      {items.map((ev) => (
        <EventListRow key={ev.id} event={ev} />
      ))}
    </div>
  );
}

export function EventsListSections({ items }: { items: EventListItem[] }) {
  const { withSummary, withoutSummary } = useMemo(() => {
    const sorted = sortByRecentDesc(items);
    return {
      withSummary: sorted.filter((e) => resolveHasSummary(e)),
      withoutSummary: sorted.filter((e) => !resolveHasSummary(e)),
    };
  }, [items]);

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3 px-1">
          <h2 className="text-base font-medium text-zinc-800">已有摘要 · 可推送</h2>
          <Badge className="border-emerald-500/30 bg-emerald-500/10 text-emerald-700">
            {withSummary.length}
          </Badge>
          <p className="text-xs text-zinc-700">已生成通稿 · 时间倒序</p>
        </div>
        <EventList items={withSummary} />
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3 px-1">
          <h2 className="text-base font-medium text-zinc-800">未写摘要 · 暂不可推送</h2>
          <Badge className="border-amber-500/30 bg-amber-500/10 text-amber-800">
            {withoutSummary.length}
          </Badge>
          <p className="text-xs text-zinc-700">尚无通稿 · 时间倒序</p>
        </div>
        <EventList items={withoutSummary} />
      </section>
    </div>
  );
}
