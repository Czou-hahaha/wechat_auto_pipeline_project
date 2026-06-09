"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ImportanceBadge } from "@/components/events/importance-badge";
import { Badge } from "@/components/ui/badge";
import { CardStatic } from "@/components/ui/card";
import { formatDate } from "@/lib/utils";
import type { EventListItem } from "@/types/event";

export function EventCard({ event, index = 0 }: { event: EventListItem; index?: number }) {
  const pushed = Boolean(event.wechatDraftPushedAt?.trim());

  return (
    <motion.div
      initial={false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <Link href={`/events/${event.id}`}>
        <CardStatic className="glass-hover block cursor-pointer transition-shadow hover:shadow-xl hover:shadow-black/30">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="flex flex-wrap gap-1.5">
              {event.hasSummary ? (
                <Badge className="border-emerald-500/30 bg-emerald-500/10 text-[10px] text-emerald-700">
                  已有摘要
                </Badge>
              ) : (
                <Badge className="border-amber-500/30 bg-amber-500/10 text-[10px] text-amber-800">
                  无摘要
                </Badge>
              )}
              {pushed ? (
                <Badge className="border-sky-500/30 bg-sky-500/10 text-[10px] text-sky-700">
                  已推草稿
                </Badge>
              ) : null}
            </div>
            <ImportanceBadge score={event.importance_score} />
          </div>

          <h3 className="mt-2 text-sm font-medium leading-snug text-zinc-900 line-clamp-2">
            {event.title}
          </h3>

          {event.titleZh ? (
            <p className="mt-1.5 text-xs leading-relaxed text-zinc-700 line-clamp-2">
              {event.titleZh}
            </p>
          ) : null}

          {event.hasSummary && event.summaryPreview ? (
            <p className="mt-2 text-xs text-zinc-700 line-clamp-2">{event.summaryPreview}</p>
          ) : null}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-zinc-700">
              {event.seed_article_count ?? event.article_count} 主稿
              {(event.expansion_article_count ?? 0) > 0
                ? ` · +${event.expansion_article_count} 扩搜`
                : ""}
              {event.enhancement_inserted != null &&
              event.enhancement_inserted > 0 &&
              (event.expansion_article_count ?? 0) === 0
                ? ` · 增强 +${event.enhancement_inserted}`
                : ""}
              {" · "}QA {event.qa_score}
            </span>
            {pushed && event.wechatDraftPushedAt ? (
              <span className="text-[10px] text-sky-700/90">
                推送 {formatDate(event.wechatDraftPushedAt)}
              </span>
            ) : null}
            {event.keywords.slice(0, 3).map((k) => (
              <Badge key={k} variant="muted">
                {k}
              </Badge>
            ))}
          </div>
        </CardStatic>
      </Link>
    </motion.div>
  );
}
