"use client";

import Link from "next/link";
import { ImportanceBadge } from "@/components/events/importance-badge";
import { Badge } from "@/components/ui/badge";
import {
  badgeDraft,
  badgeExpand,
  badgeReady,
  textMeta,
} from "@/lib/content-text";
import {
  resolveEventSegment,
  resolvePushed,
  shortArticleMeta,
} from "@/lib/event-tags";
import { formatDate } from "@/lib/utils";
import type { EventListItem } from "@/types/event";

function SegmentBadge({ segment }: { segment: ReturnType<typeof resolveEventSegment> }) {
  if (!segment) return null;
  if (segment === "可推送") {
    return <Badge className={badgeReady}>可推送</Badge>;
  }
  if (segment === "草稿已推") {
    return <Badge className={badgeDraft}>草稿已推</Badge>;
  }
  return <Badge className={badgeExpand}>待扩搜</Badge>;
}

export function EventListRow({ event }: { event: EventListItem }) {
  const segment = resolveEventSegment(event);
  const pushed = resolvePushed(event);
  const meta = shortArticleMeta(event);

  return (
    <Link
      href={`/events/${event.id}`}
      className="flex items-center gap-3 border-b border-zinc-200 px-3 py-2.5 transition-colors last:border-b-0 hover:bg-zinc-50"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <SegmentBadge segment={segment} />
          {event.createdAt ? (
            <span className={`tabular-nums ${textMeta}`}>{formatDate(event.createdAt)}</span>
          ) : null}
        </div>
        <p className="mt-0.5 truncate text-sm font-medium text-zinc-900">{event.title}</p>
        <p className={`mt-0.5 ${textMeta}`}>
          {meta}
          {segment === "可推送" && event.qa_score > 0 ? ` · QA ${event.qa_score}` : null}
          {pushed && event.wechatDraftPushedAt ? (
            <span className="text-sky-700">
              {" "}
              · 草稿 {formatDate(event.wechatDraftPushedAt)}
            </span>
          ) : null}
        </p>
      </div>
      <ImportanceBadge score={event.importance_score} />
    </Link>
  );
}
