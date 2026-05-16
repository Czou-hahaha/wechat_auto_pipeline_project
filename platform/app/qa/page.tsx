"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { useQAReviews } from "@/hooks/use-events";
import { CardStatic } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, riskColor } from "@/lib/utils";

export default function QAPage() {
  const [minScore, setMinScore] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { data, isLoading } = useQAReviews(minScore, 100);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">QA Review</h1>
        <p className="mt-1 text-sm text-zinc-500">通稿质量控制与重写追溯</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {[0, 70, 80, 90].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setMinScore(s)}
            className={cn(
              "rounded-lg border px-3 py-1.5 text-xs transition-colors",
              minScore === s
                ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
                : "border-white/[0.06] text-zinc-500 hover:text-zinc-300",
            )}
          >
            Score ≥ {s}
          </button>
        ))}
      </div>

      {isLoading ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="space-y-3">
          {data?.items.map((item, i) => (
            <motion.div
              key={item.eventId}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.03 }}
            >
              <CardStatic>
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <Link
                      href={`/events/${item.eventId}`}
                      className="text-sm font-medium text-zinc-200 hover:text-sky-400"
                    >
                      {item.title}
                    </Link>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs">
                      <span className="text-zinc-500">
                        QA{" "}
                        <span className="text-zinc-200">{item.qa.score}</span>
                      </span>
                      <span className={riskColor(item.qa.hallucinationRisk)}>
                        Risk: {item.qa.hallucinationRisk}
                      </span>
                      <span className="text-zinc-500">
                        Rewrite: {item.qa.rewriteTriggered ? "是" : "否"}
                      </span>
                      <span className="text-zinc-500">
                        AI-style: {item.qa.aiStyleRisk}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() =>
                      setExpanded(expanded === item.eventId ? null : item.eventId)
                    }
                    className="text-xs text-sky-400"
                  >
                    {expanded === item.eventId ? "收起 diff" : "查看 diff"}
                  </button>
                </div>
                {expanded === item.eventId && (
                  <div className="mt-4 grid gap-3 border-t border-white/[0.06] pt-4 md:grid-cols-2">
                    {item.rewrite_history.map((r) => (
                      <div key={r.round} className="rounded-lg bg-white/[0.02] p-3">
                        <p className="text-[10px] text-zinc-600 mb-2">
                          Round {r.round} · {r.reason}
                        </p>
                        {r.before && (
                          <pre className="whitespace-pre-wrap text-xs text-rose-300/70">
                            {r.before}
                          </pre>
                        )}
                        <pre className="mt-2 whitespace-pre-wrap text-xs text-emerald-300/80">
                          {r.after}
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </CardStatic>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
