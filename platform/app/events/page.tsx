"use client";

import { Suspense } from "react";
import { textCaption, textPageDesc } from "@/lib/content-text";
import { useFilteredEvents } from "@/hooks/use-filtered-events";
import { useEventFiltersStore } from "@/store/event-filters";
import { EventsPaginatedList } from "@/features/events/events-paginated-list";
import { Skeleton } from "@/components/ui/skeleton";

export default function EventsPage() {
  const { query, keyword, minImportance, sort, setQuery, setKeyword, setMinImportance, setSort } =
    useEventFiltersStore();
  const { items, isLoading, isFetching } = useFilteredEvents({
    q: query,
    keyword,
    minImportance,
    sort,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">Events</h1>
        <p className={`mt-1 ${textPageDesc}`}>
          可推送 / 草稿已推 / 待扩搜 · 仅跟踪草稿箱，不判断已发表
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="搜索事件…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="glass min-w-[200px] flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-sky-400 focus:outline-none"
        />
        <input
          type="text"
          placeholder="关键词"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="glass w-32 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          className="glass rounded-lg border border-zinc-200 bg-white px-3 py-2 text-sm text-zinc-800"
        >
          <option value="importance">重要性</option>
          <option value="recent">最新</option>
          <option value="qa">QA 分</option>
        </select>
        <label className={`flex items-center gap-2 ${textCaption}`}>
          最低重要性
          <input
            type="range"
            min={0}
            max={100}
            value={minImportance}
            onChange={(e) => setMinImportance(Number(e.target.value))}
            className="w-24 accent-sky-600"
          />
          {minImportance}
          {isFetching && !isLoading ? (
            <span className="text-zinc-700">筛选中…</span>
          ) : null}
        </label>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-14 w-full" />
          ))}
        </div>
      ) : items.length ? (
        <Suspense fallback={<p className={textPageDesc}>加载列表…</p>}>
          <EventsPaginatedList items={items} />
        </Suspense>
      ) : (
        <p className={textPageDesc}>暂无事件，请先运行采集。</p>
      )}
    </div>
  );
}
