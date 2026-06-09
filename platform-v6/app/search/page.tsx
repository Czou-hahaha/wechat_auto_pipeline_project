"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Search } from "lucide-react";
import { textPageDesc } from "@/lib/content-text";
import { useSearchQuery } from "@/hooks/use-events";
import { useSearchStore } from "@/store/search";
import { EventsPaginatedList } from "@/features/events/events-paginated-list";

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
        <p className={`mt-2 ${textPageDesc}`}>
          在<strong className="font-semibold text-zinc-800">已入库事件</strong>中搜索：同时匹配标题、摘要与关键词，
          按相关度排序。配置 RSS / GDELT 抓取词表请前往「采集配置」。
        </p>
      </motion.div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim() || "低空");
        }}
        className="glass flex items-center gap-3 rounded-2xl border border-zinc-200 px-4 py-3 shadow-md shadow-zinc-200/60"
      >
        <Search className="h-5 w-5 text-zinc-500" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入主题词，如 eVTOL、低空经济、无人机…"
          className="flex-1 bg-transparent text-sm text-zinc-900 placeholder:text-zinc-400 focus:outline-none"
        />
        <button
          type="submit"
          className="rounded-lg bg-sky-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-sky-500"
        >
          搜索
        </button>
      </form>

      {isFetching && (
        <p className={`text-center ${textPageDesc}`}>检索中…</p>
      )}

      {data && data.items.length > 0 && (
        <EventsPaginatedList items={data.items} />
      )}

      {data && submitted && data.items.length === 0 && (
        <p className={`text-center ${textPageDesc}`}>无匹配事件</p>
      )}
    </div>
  );
}
