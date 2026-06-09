"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { textCaption, textMeta, textMetaSm, textPageDesc } from "@/lib/content-text";
import { useQAReviews } from "@/hooks/use-events";
import { CardStatic } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { QAScoreRing } from "@/components/events/qa-score-ring";
import { cn } from "@/lib/utils";

export default function QAPage() {
  const [minScore, setMinScore] = useState(70);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, isLoading } = useQAReviews(0, 100);

  const filtered = useMemo(
    () => (data?.items ?? []).filter((item) => item.qa.score >= minScore),
    [data?.items, minScore],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">QA Review</h1>
        <p className={`mt-1 ${textPageDesc}`}>按通稿质量分数筛选事件</p>
      </div>

      <CardStatic className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="text-sm text-zinc-700">
            仅显示 QA 分数 ≥
            <span className="ml-2 tabular-nums text-lg font-semibold text-sky-700">
              {minScore}
            </span>
            分的事件
          </label>
          <span className={textCaption}>
            共 {filtered.length} / {data?.items.length ?? 0} 条
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={100}
          step={1}
          value={minScore}
          onChange={(e) => setMinScore(Number(e.target.value))}
          className="h-2 w-full cursor-pointer appearance-none rounded-full bg-zinc-200 accent-sky-600"
        />
        <div className={`flex justify-between ${textMeta}`}>
          <span>0</span>
          <span>50</span>
          <span>100</span>
        </div>
      </CardStatic>

      {isLoading ? (
        <Skeleton className="h-64" />
      ) : filtered.length === 0 ? (
        <CardStatic className={`py-12 text-center ${textPageDesc}`}>
          没有分数 ≥ {minScore} 的通稿，请调低滑块或先完成采集
        </CardStatic>
      ) : (
        <div className="overflow-hidden rounded-xl border border-zinc-200">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className={`border-b border-zinc-200 bg-zinc-50 uppercase tracking-wider ${textMetaSm}`}>
                <th className="px-4 py-2.5 font-medium text-zinc-700">事件</th>
                <th className="w-24 px-4 py-2.5 font-medium text-zinc-700">QA 分</th>
                <th className="w-28 px-4 py-2.5 text-right font-medium text-zinc-700">操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, i) => (
                <motion.tr
                  key={item.eventId}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: i * 0.02 }}
                  className="border-b border-zinc-100 hover:bg-zinc-50"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/events/${item.eventId}`}
                      className="font-medium text-zinc-800 hover:text-sky-700 line-clamp-2"
                    >
                      {item.title}
                    </Link>
                    {expanded === item.eventId && (
                      <div className="mt-3 grid gap-2 border-t border-zinc-200 pt-3 md:grid-cols-2">
                        {item.rewrite_history.map((r) => (
                          <div
                            key={r.round}
                            className={`rounded-lg bg-zinc-50 p-2 ${textCaption}`}
                          >
                            <p className={textMeta}>
                              第 {r.round} 轮 · {r.reason}
                            </p>
                            {r.after && (
                              <p className="mt-1 line-clamp-4 text-zinc-700">{r.after}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <QAScoreRing score={item.qa.score} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() =>
                        setExpanded(
                          expanded === item.eventId ? null : item.eventId,
                        )
                      }
                      className={cn(
                        "text-xs text-sky-700 hover:text-sky-800",
                        expanded === item.eventId && "text-zinc-600",
                      )}
                    >
                      {expanded === item.eventId ? "收起" : "重写记录"}
                    </button>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
