"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { useSearchQuery } from "@/hooks/use-events";
import { useSearchStore } from "@/store/search";
import { EventCard } from "@/features/events/event-card";

export default function SearchPage() {
  const { query, setQuery } = useSearchStore();
  const [submitted, setSubmitted] = useState("eVTOL");
  const { data, isFetching } = useSearchQuery(submitted);

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-center"
      >
        <h1 className="text-2xl font-semibold text-gradient-subtle">事件检索</h1>
        <p className="mt-2 text-sm text-zinc-500">
          在<strong className="text-zinc-400">已入库事件</strong>中搜索：同时匹配标题、摘要与关键词，
          按相关度排序。配置 RSS / GDELT 抓取词表请前往「采集配置」。
        </p>
      </motion.div>

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
          placeholder="输入主题词，如 eVTOL、低空经济、无人机…"
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
            共 {data.total} 个事件 · 标题优先，其次关键词与摘要
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
