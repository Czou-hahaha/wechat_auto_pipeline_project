"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { useSearchQuery } from "@/hooks/use-events";
import { useSearchStore, type SearchMode } from "@/store/search";
import { EventCard } from "@/features/events/event-card";
import { cn } from "@/lib/utils";

const MODES: { id: SearchMode; label: string }[] = [
  { id: "semantic", label: "Semantic" },
  { id: "event", label: "Event" },
  { id: "keyword", label: "Keyword" },
];

export default function SearchPage() {
  const { query, mode, setQuery, setMode } = useSearchStore();
  const [submitted, setSubmitted] = useState("eVTOL");
  const { data, isFetching } = useSearchQuery(submitted, mode);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h1 className="text-2xl font-semibold text-gradient-subtle">Search</h1>
        <p className="mt-2 text-sm text-zinc-500">
          在<strong className="text-zinc-400">已入库事件</strong>中检索（不是配置采集词表）。
          管理抓取来源与关键词请前往「采集配置」。
        </p>
      </motion.div>

      <div className="flex justify-center gap-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={cn(
              "rounded-full border px-4 py-1.5 text-xs transition-colors",
              mode === m.id
                ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
                : "border-white/[0.06] text-zinc-500",
            )}
          >
            {m.label}
          </button>
        ))}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim() || "低空");
        }}
        className="glass flex items-center gap-3 rounded-2xl border border-white/[0.08] px-4 py-3 shadow-xl shadow-black/40"
      >
        <Search className="h-5 w-5 text-zinc-500" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索事件、关键词、语义…"
          className="flex-1 bg-transparent text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-lg bg-sky-500/20 px-4 py-1.5 text-xs font-medium text-sky-300 hover:bg-sky-500/30"
        >
          搜索
        </button>
      </form>

      {isFetching && (
        <p className="text-center text-xs text-zinc-600">检索中…</p>
      )}

      {data && data.items.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs text-zinc-600">
            {data.total} 个事件 · 模式 {data.mode}
          </p>
          {data.items.map((ev, i) => (
            <EventCard key={ev.id} event={ev} index={i} />
          ))}
        </div>
      )}

      {data && submitted && data.items.length === 0 && (
        <p className="text-center text-sm text-zinc-600">无匹配事件</p>
      )}
    </div>
  );
}
