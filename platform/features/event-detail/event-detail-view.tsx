"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ExternalLink,
  GitBranch,
  Loader2,
  MessageSquare,
  Network,
  Pencil,
  RotateCw,
  Save,
  Send,
  X,
} from "lucide-react";
import { useEvent } from "@/hooks/use-events";
import { EventDetailSkeleton } from "./event-detail-skeleton";
import { ImportanceBadge } from "@/components/events/importance-badge";
import { QAScoreRing } from "@/components/events/qa-score-ring";
import { Badge } from "@/components/ui/badge";
import { CardStatic } from "@/components/ui/card";
import { pressBodyForPublish } from "@/lib/press-text";
import { cn, formatDate } from "@/lib/utils";
import type {
  EventIntelligence,
  EventHistoryPayload,
  EventMapPayload,
  EventMemorySnapshot,
  GroundingSpan,
  SourceArticle,
} from "@/types/event";

const ARTICLE_BOX_HEIGHT = "min(58vh, 560px)";
const SUPPLEMENTAL_BOX_HEIGHT = "min(32vh, 300px)";

function articleHref(url: string): string {
  const u = (url || "").trim();
  if (!u) return "#";
  if (u.startsWith("http://") || u.startsWith("https://")) return u;
  return `https://${u.replace(/^\/+/, "")}`;
}

type RefSegment = {
  index: number;
  text: string;
  sources: SourceArticle[];
};

function segmentsFromPress(
  press: string,
  grounding: GroundingSpan[],
): RefSegment[] {
  const parts = press
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (!parts.length) return [{ index: 0, text: "", sources: [] }];
  return parts.map((text, i) => ({
    index: i,
    text,
    sources: grounding[i]?.sources?.length
      ? (grounding[i].sources as SourceArticle[])
      : [],
  }));
}

function groupArticles(articles: SourceArticle[]) {
  const seed = articles.filter((a) => a.sourceKind === "seed");
  const supplemental = articles
    .filter((a) => a.sourceKind !== "seed")
    .sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0));
  return { seed, supplemental };
}

function similarityPercent(sim: number | undefined): number {
  const v = sim ?? 0;
  return v > 1 ? Math.round(v) : Math.round(v * 100);
}

export function EventDetailView({ id }: { id: string }) {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useEvent(id);
  const [titleDraft, setTitleDraft] = useState("");
  const [pressDraft, setPressDraft] = useState("");
  const [isEditing, setIsEditing] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTitle, setDrawerTitle] = useState("");
  const [drawerSources, setDrawerSources] = useState<SourceArticle[]>([]);
  const [saving, setSaving] = useState(false);
  const [pushing, setPushing] = useState(false);
  const [actionMsg, setActionMsg] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const [eventMap, setEventMap] = useState<EventMapPayload | null>(null);
  const [memory, setMemory] = useState<EventMemorySnapshot | null>(null);
  const [loadingInsight, setLoadingInsight] = useState(false);
  const [refreshingMemory, setRefreshingMemory] = useState(false);
  const [feedbackCategory, setFeedbackCategory] = useState("general");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const [eventHistory, setEventHistory] = useState<EventHistoryPayload | null>(null);

  const event = data as EventIntelligence | undefined;

  useEffect(() => {
    if (!event) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTitleDraft(event.title || "");
    setPressDraft(event.summary || "");
    setIsEditing(false);
  }, [event]);

  useEffect(() => {
    if (!id) return;
    let mounted = true;
    const loadInsight = async () => {
      setLoadingInsight(true);
      try {
        const [mapRes, memoryRes, historyRes] = await Promise.all([
          fetch(`/api/events/${id}/map`),
          fetch(`/api/events/${id}/memory`),
          fetch(`/api/events/${id}/history`),
        ]);
        if (!mounted) return;
        const mapBody = await mapRes.json().catch(() => null);
        const memoryBody = await memoryRes.json().catch(() => null);
        const historyBody = await historyRes.json().catch(() => null);
        setEventMap(mapRes.ok ? (mapBody as EventMapPayload) : null);
        setMemory(memoryRes.ok ? (memoryBody as EventMemorySnapshot) : null);
        setEventHistory(historyRes.ok ? (historyBody as EventHistoryPayload) : null);
      } finally {
        if (mounted) setLoadingInsight(false);
      }
    };
    void loadInsight();
    return () => {
      mounted = false;
    };
  }, [id]);

  const { seed, supplemental } = useMemo(
    () => groupArticles(event?.articles ?? []),
    [event?.articles],
  );
  const primarySeed = seed[0];

  const segments = useMemo(
    () => segmentsFromPress(pressDraft, event?.grounding ?? []),
    [pressDraft, event?.grounding],
  );

  function openRefs(title: string, sources: SourceArticle[]) {
    setDrawerTitle(title);
    setDrawerSources(sources);
    setDrawerOpen(true);
  }

  if (isLoading) return <EventDetailSkeleton />;
  if (error || !event)
    return (
      <CardStatic className="p-8 text-center">
        <p className="text-zinc-700">事件未找到</p>
        <Link href="/events" className="mt-4 inline-block text-sm text-sky-700">
          返回 Events
        </Link>
      </CardStatic>
    );

  async function savePress() {
    setSaving(true);
    setActionMsg(null);
    try {
      const res = await fetch(`/api/events/${id}/press`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: titleDraft,
          summary: pressBodyForPublish(pressDraft),
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error((body as { detail?: string }).detail || "保存失败");
      setActionMsg({ ok: true, text: "通稿已保存" });
      setIsEditing(false);
      await refetch();
      qc.invalidateQueries({ queryKey: ["events"] });
    } catch (e) {
      setActionMsg({
        ok: false,
        text: e instanceof Error ? e.message : "保存失败",
      });
    } finally {
      setSaving(false);
    }
  }

  async function markDraftPushed() {
    setPushing(true);
    setActionMsg(null);
    try {
      const res = await fetch(`/api/events/${id}/mark-draft-pushed`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const body = (await res.json()) as { detail?: string; pushedAt?: string };
      if (!res.ok) throw new Error(body.detail || "标记失败");
      setActionMsg({
        ok: true,
        text: body.pushedAt
          ? `已标记草稿已推 · ${formatDate(body.pushedAt)}`
          : "已标记为草稿已推",
      });
      await refetch();
      await qc.invalidateQueries({ queryKey: ["events"] });
      window.location.href = "/events?segment=草稿已推";
    } catch (e) {
      const msg = e instanceof Error ? e.message : "标记失败";
      setActionMsg({
        ok: false,
        text: msg.includes("404") || msg.includes("Not Found")
          ? "标记失败：BFF 未更新，请重启 V3 BFF（:8787）后重试"
          : msg,
      });
    } finally {
      setPushing(false);
    }
  }

  async function pushDraft() {
    setPushing(true);
    setActionMsg(null);
    try {
      const res = await fetch(`/api/events/${id}/push-draft`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: titleDraft,
          summary: pressBodyForPublish(pressDraft),
        }),
      });
      const body = (await res.json()) as { detail?: string };
      if (!res.ok) throw new Error(body.detail || "推送失败");
      const pushedAt =
        typeof (body as { pushedAt?: string }).pushedAt === "string"
          ? (body as { pushedAt: string }).pushedAt
          : "";
      setActionMsg({
        ok: true,
        text: pushedAt
          ? `推送成功 · ${formatDate(pushedAt)}`
          : "已写入公众号草稿箱",
      });
      await refetch();
      await qc.invalidateQueries({ queryKey: ["events"] });
      window.location.href = "/events?segment=草稿已推";
    } catch (e) {
      setActionMsg({
        ok: false,
        text: e instanceof Error ? e.message : "推送失败",
      });
    } finally {
      setPushing(false);
    }
  }

  async function refreshMemory() {
    setRefreshingMemory(true);
    try {
      const res = await fetch(`/api/events/${id}/memory`, { method: "POST" });
      const body = (await res.json().catch(() => ({}))) as {
        snapshot?: EventMemorySnapshot;
      };
      if (!res.ok || !body.snapshot) throw new Error("记忆刷新失败");
      setMemory(body.snapshot);
      setActionMsg({ ok: true, text: "事件记忆已刷新" });
    } catch (e) {
      setActionMsg({
        ok: false,
        text: e instanceof Error ? e.message : "记忆刷新失败",
      });
    } finally {
      setRefreshingMemory(false);
    }
  }

  async function submitFeedback() {
    if (!feedbackNote.trim()) return;
    setSubmittingFeedback(true);
    setFeedbackMsg(null);
    try {
      const res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          eventId: id,
          stage: "qa",
          category: feedbackCategory,
          note: feedbackNote.trim(),
        }),
      });
      if (!res.ok) throw new Error("反馈提交失败");
      setFeedbackNote("");
      setFeedbackMsg({ ok: true, text: "反馈已提交，后续可用于QA与筛选策略迭代" });
    } catch (e) {
      setFeedbackMsg({
        ok: false,
        text: e instanceof Error ? e.message : "反馈提交失败",
      });
    } finally {
      setSubmittingFeedback(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link
        href="/events"
        className="inline-flex items-center gap-2 text-sm text-zinc-700 hover:text-zinc-700"
      >
        <ArrowLeft className="h-4 w-4" />
        返回 Events
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="min-w-0 flex-1 text-2xl font-semibold leading-snug text-zinc-900">
          {event.title}
        </h1>
        <div className="flex items-center gap-3">
          <ImportanceBadge score={event.importance_score} />
          {event.qa_score > 0 && <QAScoreRing score={event.qa_score} />}
        </div>
      </div>

      {primarySeed ? (
        <SeedBanner article={primarySeed} totalSeeds={seed.length} />
      ) : (
        <p className="text-xs text-zinc-700">暂无溯源主稿</p>
      )}

      <CardStatic className="flex flex-col gap-0 overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsEditing((v) => !v)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                isEditing
                  ? "bg-sky-500 text-white"
                  : "border border-zinc-200 text-zinc-700 hover:bg-zinc-50",
              )}
            >
              <Pencil className="h-3.5 w-3.5" />
              {isEditing ? "阅读" : "编辑"}
            </button>
            <span className="text-xs text-zinc-700">
              {isEditing ? "编辑模式" : "阅读模式 · 点击文中〔n〕查看引用"}
            </span>
          </div>
          {event.wechatDraftPushedAt ? (
            <Badge className="border-emerald-500/30 text-emerald-700">
              已推草稿 · {formatDate(event.wechatDraftPushedAt)}
            </Badge>
          ) : null}
        </div>

        {isEditing && (
          <div className="border-b border-zinc-200 px-4 py-2">
            <label className="text-[11px] text-zinc-700">推送标题</label>
            <input
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              className="input-field mt-1 w-full text-sm"
            />
          </div>
        )}

        <div
          className="overflow-y-auto px-5 py-4"
          style={{ height: ARTICLE_BOX_HEIGHT }}
        >
          {isEditing ? (
            <textarea
              value={pressDraft}
              onChange={(e) => setPressDraft(e.target.value)}
              className="input-field h-full min-h-full w-full resize-none border-0 bg-transparent font-sans text-sm leading-[1.85] text-zinc-800 focus:ring-0"
              style={{ minHeight: ARTICLE_BOX_HEIGHT }}
            />
          ) : (
            <ArticleReader
              segments={segments}
              onRefClick={(label, sources) => openRefs(label, sources)}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-zinc-200 px-4 py-3">
          <button
            type="button"
            onClick={savePress}
            disabled={saving || pushing}
            className="inline-flex items-center gap-2 rounded-lg border border-zinc-200 px-4 py-2 text-sm text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            保存通稿
          </button>
          <button
            type="button"
            onClick={pushDraft}
            disabled={saving || pushing || !pressDraft.trim()}
            className="inline-flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm text-white hover:bg-sky-400 disabled:opacity-50"
          >
            {pushing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            推送草稿箱
          </button>
          {!event.wechatDraftPushedAt ? (
            <button
              type="button"
              onClick={markDraftPushed}
              disabled={saving || pushing}
              className="inline-flex items-center gap-2 rounded-lg border border-sky-500/30 px-4 py-2 text-sm text-sky-700 hover:bg-sky-500/10 disabled:opacity-50"
              title="已在微信公众平台手工写入草稿、但未走本系统推送时使用"
            >
              标记草稿已推
            </button>
          ) : null}
          {actionMsg && (
            <p
              className={cn(
                "text-sm",
                actionMsg.ok ? "text-emerald-700" : "text-rose-700",
              )}
            >
              {actionMsg.text}
            </p>
          )}
        </div>
      </CardStatic>

      {supplemental.length > 0 && (
        <SupplementalArticlesPanel articles={supplemental} />
      )}

      <CardStatic className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-zinc-700" />
          <h3 className="text-sm font-medium text-zinc-700">历史关联事件链 + 连续报告</h3>
        </div>
        {eventHistory && eventHistory.chain.length > 0 ? (
          <div className="space-y-2 text-xs text-zinc-700">
            <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">关联事件链</p>
              <ul className="space-y-1">
                {eventHistory.chain.map((node) => (
                  <li key={node.eventId} className="flex items-center gap-2">
                    <span className="tabular-nums text-[10px]">
                      {node.createdAt ? node.createdAt.slice(0, 10) : "未知时间"}
                    </span>
                    <span className={node.relation === "current" ? "text-sky-700" : ""}>
                      {node.title}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">连续报告</p>
              <p className="whitespace-pre-wrap leading-relaxed">
                {eventHistory.timelineReport || "暂无连续报告"}
              </p>
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-700">暂无足够历史关联事件。</p>
        )}
      </CardStatic>

      <CardStatic className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <Network className="h-4 w-4 text-zinc-700" />
          <h3 className="text-sm font-medium text-zinc-700">事件地图（V5 MVP）</h3>
        </div>
        {loadingInsight ? (
          <p className="text-xs text-zinc-700">加载中…</p>
        ) : eventMap ? (
          <div className="space-y-2 text-xs text-zinc-700">
            <p>
              节点 {eventMap.nodeCount} · 边 {eventMap.edgeCount} · 来源多样性{" "}
              {eventMap.sourceDiversity}
            </p>
            {eventMap.topSources.length > 0 ? (
              <p>
                主要来源：
                {eventMap.topSources
                  .slice(0, 5)
                  .map((x) => `${x.host}(${x.count})`)
                  .join("、")}
              </p>
            ) : null}
            <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">证据片段</p>
              <ul className="space-y-1">
                {(eventMap.evidence || []).slice(0, 3).map((ev, idx) => (
                  <li key={`${ev.url}-${idx}`} className="line-clamp-2">
                    [{ev.sourceHost || "unknown"}] {ev.snippet}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-700">暂无事件地图数据</p>
        )}
      </CardStatic>

      <CardStatic className="p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <RotateCw className="h-4 w-4 text-zinc-700" />
            <h3 className="text-sm font-medium text-zinc-700">事件记忆（V5 MVP）</h3>
          </div>
          <button
            type="button"
            onClick={refreshMemory}
            disabled={refreshingMemory}
            className="rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
          >
            {refreshingMemory ? "刷新中…" : "刷新记忆"}
          </button>
        </div>
        {memory ? (
          <div className="space-y-2 text-xs text-zinc-700">
            <p>
              QA 分数 {memory.qa_score} · 停止原因 {memory.qa_stopped_reason || "n/a"}
            </p>
            <p>更新时间 {formatDate(memory.updated_at)}</p>
            <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-2">
              <p className="mb-1 text-[11px] text-zinc-700">事实快照</p>
              <ul className="space-y-1">
                {memory.facts.slice(0, 3).map((fact, idx) => (
                  <li key={`${fact.source_url}-${idx}`} className="line-clamp-1">
                    {fact.title}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-700">暂无记忆快照，点击“刷新记忆”生成。</p>
        )}
      </CardStatic>

      <CardStatic className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-zinc-700" />
          <h3 className="text-sm font-medium text-zinc-700">反馈回流（V5 MVP）</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            value={feedbackCategory}
            onChange={(e) => setFeedbackCategory(e.target.value)}
            className="input-field text-xs"
          >
            <option value="general">通用反馈</option>
            <option value="factual_error">事实错误</option>
            <option value="off_topic">主题偏离</option>
            <option value="citation_gap">引用不足</option>
            <option value="style_issue">表达问题</option>
          </select>
          <input
            value={feedbackNote}
            onChange={(e) => setFeedbackNote(e.target.value)}
            className="input-field min-w-[240px] flex-1 text-xs"
            placeholder="填写人工反馈，供QA与筛选策略迭代"
          />
          <button
            type="button"
            onClick={submitFeedback}
            disabled={submittingFeedback || !feedbackNote.trim()}
            className="rounded-md bg-sky-500 px-3 py-1.5 text-xs text-white hover:bg-sky-400 disabled:opacity-50"
          >
            {submittingFeedback ? "提交中…" : "提交反馈"}
          </button>
        </div>
        {feedbackMsg ? (
          <p className={cn("mt-2 text-xs", feedbackMsg.ok ? "text-emerald-700" : "text-rose-700")}>
            {feedbackMsg.text}
          </p>
        ) : null}
      </CardStatic>

      <CitationDrawer
        open={drawerOpen}
        title={drawerTitle}
        sources={drawerSources}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
}

function SeedBanner({
  article,
  totalSeeds,
}: {
  article: SourceArticle;
  totalSeeds: number;
}) {
  return (
    <CardStatic className="px-4 py-3">
      <p className="text-[11px] font-medium text-sky-700/90">
        溯源主稿
        {totalSeeds > 1 ? (
          <span className="ml-2 font-normal text-zinc-700">
            展示首篇，共 {totalSeeds} 篇
          </span>
        ) : null}
      </p>
      <a
        href={articleHref(article.url)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1.5 inline-flex items-start gap-1.5 text-sm text-sky-700 hover:text-sky-700 hover:underline"
      >
        <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0" />
        <span className="line-clamp-2">{article.title}</span>
      </a>
      <p className="mt-1 text-[10px] text-zinc-700">
        {article.sourceHost}
        {article.publishedAt ? ` · ${formatDate(article.publishedAt)}` : ""}
      </p>
    </CardStatic>
  );
}

function SupplementalArticlesPanel({
  articles,
}: {
  articles: SourceArticle[];
}) {
  return (
    <CardStatic className="overflow-hidden p-0">
      <div className="border-b border-zinc-200 px-4 py-3">
        <h2 className="text-sm font-medium text-zinc-700">
          参考稿（扩搜 / 聚类关联）
        </h2>
        <p className="mt-0.5 text-[11px] text-zinc-700">
          与主稿同源、经不同检索阶段收录，共 {articles.length} 篇 · 下滑查看
        </p>
      </div>
      <div
        className="overflow-y-auto px-4 py-3"
        style={{ height: SUPPLEMENTAL_BOX_HEIGHT }}
      >
        <ul className="space-y-3">
          {articles.map((a) => {
            const pct = similarityPercent(a.similarity);
            return (
              <li
                key={a.id}
                className="rounded-lg border border-zinc-200 bg-zinc-50 p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-zinc-700">
                    {a.sourceKind === "expansion" ? "扩搜" : "聚类关联"}
                  </span>
                  <span
                    className={cn(
                      "text-[11px] font-medium tabular-nums",
                      pct >= 75
                        ? "text-emerald-700"
                        : pct >= 55
                          ? "text-amber-700"
                          : "text-zinc-700",
                    )}
                    title="与事件主题的语义相似度"
                  >
                    相似度 {pct}%
                  </span>
                </div>
                <div
                  className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.06]"
                  aria-hidden
                >
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      pct >= 75
                        ? "bg-emerald-500/70"
                        : pct >= 55
                          ? "bg-amber-500/60"
                          : "bg-zinc-600",
                    )}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
                <a
                  href={articleHref(a.url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-2 inline-flex items-start gap-1.5 text-sm leading-snug text-sky-700 hover:text-sky-700 hover:underline"
                >
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {a.title}
                </a>
                <p className="mt-1 text-[10px] text-zinc-700">
                  {a.sourceHost}
                  {a.publishedAt ? ` · ${formatDate(a.publishedAt)}` : ""}
                </p>
                {a.excerpt ? (
                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-zinc-700">
                    {a.excerpt}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>
    </CardStatic>
  );
}

function ArticleReader({
  segments,
  onRefClick,
}: {
  segments: RefSegment[];
  onRefClick: (label: string, sources: SourceArticle[]) => void;
}) {
  if (!segments.some((s) => s.text)) {
    return <p className="text-sm text-zinc-700">暂无通稿正文</p>;
  }

  return (
    <article className="whitespace-pre-wrap text-sm leading-[1.85] text-zinc-800">
      {segments.map((seg, i) => (
        <span key={seg.index}>
          {seg.text}
          {seg.sources.length > 0 && (
            <button
              type="button"
              onClick={() =>
                onRefClick(`第 ${seg.index + 1} 段参考`, seg.sources)
              }
              className="mx-0.5 inline align-baseline text-[11px] font-medium text-sky-700 hover:text-sky-700"
              title="查看本段引用来源"
            >
              〔{seg.sources.length}〕
            </button>
          )}
          {i < segments.length - 1 ? "\n\n" : ""}
        </span>
      ))}
    </article>
  );
}

function CitationDrawer({
  open,
  title,
  sources,
  onClose,
}: {
  open: boolean;
  title: string;
  sources: SourceArticle[];
  onClose: () => void;
}) {
  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/40 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-zinc-200 bg-[#0c0c0e] shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
        )}
        aria-hidden={!open}
      >
        <div className="flex items-center justify-between border-b border-zinc-200 px-4 py-4">
          <h3 className="text-sm font-medium text-zinc-800">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-zinc-700 hover:bg-zinc-50 hover:text-zinc-700"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {sources.length === 0 ? (
            <p className="text-sm text-zinc-700">暂无引用来源</p>
          ) : (
            <ul className="space-y-4">
              {sources.map((a) => (
                <li
                  key={a.id}
                  className="rounded-lg border border-zinc-200 bg-zinc-50 p-3"
                >
                  <span className="text-[10px] text-zinc-700">
                    {a.sourceKind === "seed"
                      ? "溯源主稿"
                      : a.sourceKind === "expansion"
                        ? "扩搜参考"
                        : "聚类关联"}
                  </span>
                  {(a.similarity ?? 0) > 0 && (
                    <span className="ml-2 text-[10px] text-zinc-700">
                      相似度 {similarityPercent(a.similarity)}%
                    </span>
                  )}
                  <a
                    href={articleHref(a.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block text-sm leading-snug text-sky-700 hover:text-sky-700 hover:underline"
                  >
                    {a.title}
                  </a>
                  <p className="mt-1 text-[10px] text-zinc-700">{a.sourceHost}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
