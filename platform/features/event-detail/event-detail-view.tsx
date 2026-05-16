"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { useEvent } from "@/hooks/use-events";
import { useEventDetailStore } from "@/store/event-detail";
import { EventDetailSkeleton } from "./event-detail-skeleton";
import { ImportanceBadge } from "@/components/events/importance-badge";
import { QAScoreRing } from "@/components/events/qa-score-ring";
import { Badge } from "@/components/ui/badge";
import { CardStatic } from "@/components/ui/card";
import { cn, formatDate, riskColor } from "@/lib/utils";
import type { EventIntelligence, GroundingSpan } from "@/types/event";

export function EventDetailView({ id }: { id: string }) {
  const { data, isLoading, error } = useEvent(id);
  const { selectedParagraphId, rightTab, setSelectedParagraphId, setRightTab } =
    useEventDetailStore();

  if (isLoading) return <EventDetailSkeleton />;
  if (error || !data)
    return (
      <CardStatic className="p-8 text-center">
        <p className="text-zinc-400">事件未找到</p>
        <Link href="/events" className="mt-4 inline-block text-sm text-sky-400">
          返回事件列表
        </Link>
      </CardStatic>
    );

  const event = data as EventIntelligence;
  const selectedGrounding =
    event.grounding.find((g) => g.paragraphId === selectedParagraphId) ??
    event.grounding[0];

  return (
    <div className="space-y-4">
      <Link
        href="/events"
        className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300"
      >
        <ArrowLeft className="h-4 w-4" />
        返回 Events
      </Link>

      <div className="grid gap-4 xl:grid-cols-[260px_1fr_360px]">
        <EventTimelinePanel event={event} selectedParagraphId={selectedParagraphId} />
        <CenterPressPanel
          event={event}
          selectedParagraphId={selectedParagraphId}
          onSelectParagraph={setSelectedParagraphId}
        />
        <RightIntelPanel
          event={event}
          rightTab={rightTab}
          setRightTab={setRightTab}
          selectedGrounding={selectedGrounding}
        />
      </div>
    </div>
  );
}

function EventTimelinePanel({
  event,
  selectedParagraphId,
}: {
  event: EventIntelligence;
  selectedParagraphId: string | null;
}) {
  return (
    <CardStatic className="h-fit max-h-[calc(100vh-12rem)] overflow-y-auto">
      <h3 className="mb-4 text-xs font-medium uppercase tracking-wider text-zinc-500">
        Timeline
      </h3>
      <div className="relative space-y-0 border-l border-white/10 pl-4">
        {event.timeline.map((node, i) => (
          <motion.div
            key={node.id}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="relative pb-6 last:pb-0"
          >
            <span className="absolute -left-[21px] top-1.5 h-2 w-2 rounded-full bg-sky-500/80 ring-4 ring-[#0a0a0b]" />
            <p className="text-[10px] text-zinc-600">{formatDate(node.at)}</p>
            <p className="mt-0.5 text-sm text-zinc-300 line-clamp-2">{node.label}</p>
            {node.sourceHost && (
              <p className="text-[10px] text-zinc-600">{node.sourceHost}</p>
            )}
          </motion.div>
        ))}
      </div>
    </CardStatic>
  );
}

function CenterPressPanel({
  event,
  selectedParagraphId,
  onSelectParagraph,
}: {
  event: EventIntelligence;
  selectedParagraphId: string | null;
  onSelectParagraph: (id: string) => void;
}) {
  return (
    <div className="space-y-4">
      <CardStatic>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <h1 className="text-lg font-semibold leading-snug text-zinc-100">
              {event.title}
            </h1>
            <div className="mt-3 flex flex-wrap gap-2">
              <ImportanceBadge score={event.importance_score} />
              {event.countries.map((c) => (
                <Badge key={c} variant="muted">
                  {c}
                </Badge>
              ))}
              {event.keywords.slice(0, 5).map((k) => (
                <Badge key={k} variant="accent">
                  {k}
                </Badge>
              ))}
            </div>
          </div>
          <QAScoreRing score={event.qa_score} />
        </div>
      </CardStatic>

      <CardStatic>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-medium text-zinc-300">AI 新闻稿</h2>
          <span className="text-[10px] text-zinc-600">
            点击段落查看溯源
          </span>
        </div>
        <div className="space-y-3">
          {event.grounding.map((g, i) => (
            <motion.button
              key={g.paragraphId}
              type="button"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: i * 0.04 }}
              onClick={() => onSelectParagraph(g.paragraphId)}
              className={cn(
                "w-full rounded-lg border px-4 py-3 text-left text-sm leading-relaxed text-zinc-300 transition-all",
                selectedParagraphId === g.paragraphId
                  ? "border-sky-500/40 bg-sky-500/5 ring-1 ring-sky-500/20"
                  : "border-transparent bg-white/[0.02] hover:border-white/10 hover:bg-white/[0.04]",
              )}
            >
              {g.text}
            </motion.button>
          ))}
        </div>
      </CardStatic>

      <RewriteHistoryPanel history={event.rewrite_history} />
    </div>
  );
}

function RewriteHistoryPanel({
  history,
}: {
  history: EventIntelligence["rewrite_history"];
}) {
  return (
    <CardStatic>
      <h3 className="mb-3 text-sm font-medium text-zinc-400">Rewrite History</h3>
      <div className="space-y-2">
        {history.map((r) => (
          <details
            key={r.round}
            className="rounded-lg border border-white/[0.06] bg-white/[0.02] px-3 py-2"
          >
            <summary className="cursor-pointer text-xs text-zinc-400">
              Round {r.round} · {r.reason} · {formatDate(r.at)}
            </summary>
            {r.before && (
              <p className="mt-2 text-xs text-rose-300/80 line-clamp-3">{r.before}</p>
            )}
            <p className="mt-1 text-xs text-emerald-300/80 line-clamp-4">{r.after}</p>
          </details>
        ))}
      </div>
    </CardStatic>
  );
}

function RightIntelPanel({
  event,
  rightTab,
  setRightTab,
  selectedGrounding,
}: {
  event: EventIntelligence;
  rightTab: "sources" | "qa" | "grounding";
  setRightTab: (t: "sources" | "qa" | "grounding") => void;
  selectedGrounding?: GroundingSpan;
}) {
  const tabs = [
    { id: "grounding" as const, label: "溯源" },
    { id: "sources" as const, label: "来源" },
    { id: "qa" as const, label: "QA" },
  ];

  return (
    <div className="space-y-3">
      <div className="flex gap-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-1">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setRightTab(t.id)}
            className={cn(
              "flex-1 rounded-md px-2 py-1.5 text-xs transition-colors",
              rightTab === t.id
                ? "bg-white/10 text-zinc-100"
                : "text-zinc-500 hover:text-zinc-300",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {rightTab === "grounding" && (
        <CardStatic>
          <h3 className="mb-2 text-sm font-medium text-zinc-300">Source Grounding</h3>
          <p className="mb-3 text-xs text-zinc-500">
            这段内容来源于以下 source articles
          </p>
          {selectedGrounding ? (
            <>
              <p className="mb-3 rounded-md bg-white/[0.03] p-2 text-xs text-zinc-400 line-clamp-4">
                {selectedGrounding.text}
              </p>
              <p className="mb-2 text-[10px] text-zinc-600">
                置信度 {(selectedGrounding.confidence * 100).toFixed(0)}%
              </p>
              <ul className="space-y-2">
                {selectedGrounding.articleIds.map((aid) => {
                  const art = event.articles.find((a) => a.id === aid);
                  if (!art) return null;
                  return (
                    <li
                      key={aid}
                      className="rounded-lg border border-white/[0.06] p-2 text-xs"
                    >
                      <p className="font-medium text-zinc-300">{art.title}</p>
                      <p className="mt-1 text-zinc-600">{art.sourceHost}</p>
                    </li>
                  );
                })}
              </ul>
            </>
          ) : (
            <p className="text-xs text-zinc-600">选择左侧通稿段落</p>
          )}
        </CardStatic>
      )}

      {rightTab === "sources" && (
        <CardStatic className="max-h-[calc(100vh-14rem)] overflow-y-auto">
          <h3 className="mb-3 text-sm font-medium text-zinc-300">Source Articles</h3>
          <p className="mb-2 text-[10px] text-zinc-600">
            Domains: {event.sourceDomains?.join(", ")}
          </p>
          <ul className="space-y-3">
            {event.articles.map((a) => (
              <li
                key={a.id}
                className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
              >
                <motion.div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-zinc-300">{a.title}</p>
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noreferrer"
                    className="shrink-0 text-zinc-500 hover:text-sky-400"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </motion.div>
                <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/5">
                  <motion.div
                    className="h-full bg-sky-500/60"
                    initial={{ width: 0 }}
                    animate={{ width: `${a.similarity * 100}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-zinc-600">
                  相似度 {(a.similarity * 100).toFixed(0)}% · {a.sourceHost}
                </p>
                <p className="mt-2 text-xs text-zinc-500 line-clamp-2">{a.excerpt}</p>
              </li>
            ))}
          </ul>
        </CardStatic>
      )}

      {rightTab === "qa" && (
        <CardStatic>
          <h3 className="mb-3 text-sm font-medium text-zinc-300">QA Review</h3>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-zinc-500">Hallucination risk</span>
              <span className={riskColor(event.qa.hallucinationRisk)}>
                {event.qa.hallucinationRisk}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">AI-style risk</span>
              <span className="text-zinc-300">{event.qa.aiStyleRisk}</span>
            </div>
            <motion.div className="flex justify-between">
              <span className="text-zinc-500">Rewrite triggered</span>
              <span className="text-zinc-300">
                {event.qa.rewriteTriggered ? "是" : "否"}
              </span>
            </motion.div>
            {event.qa.missingFacts.length > 0 && (
              <div>
                <p className="text-zinc-500">Missing facts</p>
                <ul className="mt-1 list-inside list-disc text-xs text-amber-400/90">
                  {event.qa.missingFacts.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              </div>
            )}
            {event.qa.issues.length > 0 && (
              <div>
                <p className="text-zinc-500">Issues</p>
                <ul className="mt-1 space-y-1">
                  {event.qa.issues.map((issue, i) => (
                    <li
                      key={i}
                      className="rounded border border-white/[0.06] px-2 py-1 text-xs text-zinc-400"
                    >
                      [{issue.severity}] {issue.description}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </CardStatic>
      )}
    </div>
  );
}
