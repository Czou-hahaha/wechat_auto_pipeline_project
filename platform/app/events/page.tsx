"use client";

import { useEvents } from "@/hooks/use-events";
import { useEventFiltersStore } from "@/store/event-filters";
import { EventCard } from "@/features/events/event-card";
import { Skeleton } from "@/components/ui/skeleton";

export default function EventsPage() {
  const { query, keyword, minImportance, sort, setQuery, setKeyword, setMinImportance, setSort } =
    useEventFiltersStore();
  const { data, isLoading } = useEvents({ q: query, keyword, minImportance, sort });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">Events</h1>
        <p className="mt-1 text-sm text-zinc-500">以事件为单位的情报视图</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          placeholder="搜索事件…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="glass min-w-[200px] flex-1 rounded-lg border border-white/[0.06] bg-transparent px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-600 focus:border-sky-500/30 focus:outline-none"
        />
        <input
          type="text"
          placeholder="关键词"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          className="glass w-32 rounded-lg border border-white/[0.06] bg-transparent px-3 py-2 text-sm"
        />
        <select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          className="glass rounded-lg border border-white/[0.06] bg-transparent px-3 py-2 text-sm text-zinc-300"
        >
          <option value="importance">重要性</option>
          <option value="recent">最新</option>
          <option value="qa">QA 分</option>
        </select>
        <label className="flex items-center gap-2 text-xs text-zinc-500">
          最低重要性
          <input
            type="range"
            min={0}
            max={100}
            value={minImportance}
            onChange={(e) => setMinImportance(Number(e.target.value))}
            className="w-24"
          />
          {minImportance}
        </label>
      </div>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-36" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data?.items.map((ev, i) => (
            <EventCard key={ev.id} event={ev} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}
