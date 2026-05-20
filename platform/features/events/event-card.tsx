"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ImportanceBadge } from "@/components/events/importance-badge";
import { Badge } from "@/components/ui/badge";
import { CardStatic } from "@/components/ui/card";
import type { EventListItem } from "@/types/event";

export function EventCard({ event, index = 0 }: { event: EventListItem; index?: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <Link href={`/events/${event.id}`}>
        <CardStatic className="glass-hover block cursor-pointer transition-shadow hover:shadow-xl hover:shadow-black/30">
          <div className="flex items-start justify-between gap-3">
            <h3 className="text-sm font-medium leading-snug text-zinc-100 line-clamp-2">
              {event.title}
            </h3>
            <ImportanceBadge score={event.importance_score} />
          </div>
          <p className="mt-2 text-xs text-zinc-500 line-clamp-2">{event.summaryPreview}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <span className="text-[10px] text-zinc-600">
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
