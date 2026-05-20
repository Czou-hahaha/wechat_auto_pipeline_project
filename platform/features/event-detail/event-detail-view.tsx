"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ExternalLink,
  Loader2,
  Pencil,
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
import type { EventIntelligence, GroundingSpan, SourceArticle } from "@/types/event";

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

  const event = data as EventIntelligence | undefined;

  useEffect(() => {
    if (!event) return;
    setTitleDraft(event.title || "");
    setPressDraft(event.summary || "");
    setIsEditing(false);
  }, [event?.id, event?.summary, event?.title]);

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
        <p className="text-zinc-400">事件未找到</p>
        <Link href="/events" className="mt-4 inline-block text-sm text-sky-400">
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
      setActionMsg({ ok: true, text: "已写入公众号草稿箱" });
      await refetch();
    } catch (e) {
      setActionMsg({
        ok: false,
        text: e instanceof Error ? e.message : "推送失败",
      });
    } finally {
      setPushing(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <Link
        href="/events"
        className="inline-flex items-center gap-2 text-sm text-zinc-500 hover:text-zinc-300"
      >
        <ArrowLeft className="h-4 w-4" />
        返回 Events
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <h1 className="min-w-0 flex-1 text-2xl font-semibold leading-snug text-zinc-100">
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
        <p className="text-xs text-zinc-600">暂无溯源主稿</p>
      )}

      <CardStatic className="flex flex-col gap-0 overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsEditing((v) => !v)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                isEditing
                  ? "bg-sky-500 text-white"
                  : "border border-white/10 text-zinc-300 hover:bg-white/[0.04]",
              )}
            >
              <Pencil className="h-3.5 w-3.5" />
              {isEditing ? "阅读" : "编辑"}
            </button>
            <span className="text-xs text-zinc-600">
              {isEditing ? "编辑模式" : "阅读模式 · 点击文中〔n〕查看引用"}
            </span>
          </div>
          {event.wechatDraftPushedAt ? (
            <Badge className="border-emerald-500/30 text-emerald-300">
              已推草稿 · {formatDate(event.wechatDraftPushedAt)}
            </Badge>
          ) : null}
        </div>

        {isEditing && (
          <div className="border-b border-white/[0.06] px-4 py-2">
            <label className="text-[11px] text-zinc-500">推送标题</label>
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
              className="input-field h-full min-h-full w-full resize-none border-0 bg-transparent font-sans text-sm leading-[1.85] text-zinc-200 focus:ring-0"
              style={{ minHeight: ARTICLE_BOX_HEIGHT }}
            />
          ) : (
            <ArticleReader
              segments={segments}
              onRefClick={(label, sources) => openRefs(label, sources)}
            />
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-white/[0.06] px-4 py-3">
          <button
            type="button"
            onClick={savePress}
            disabled={saving || pushing}
            className="inline-flex items-center gap-2 rounded-lg border border-white/10 px-4 py-2 text-sm text-zinc-300 hover:bg-white/[0.04] disabled:opacity-50"
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
          {actionMsg && (
            <p
              className={cn(
                "text-sm",
                actionMsg.ok ? "text-emerald-400" : "text-rose-400",
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
      <p className="text-[11px] font-medium text-sky-300/90">
        溯源主稿
        {totalSeeds > 1 ? (
          <span className="ml-2 font-normal text-zinc-600">
            展示首篇，共 {totalSeeds} 篇
          </span>
        ) : null}
      </p>
      <a
        href={articleHref(article.url)}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1.5 inline-flex items-start gap-1.5 text-sm text-sky-400 hover:text-sky-300 hover:underline"
      >
        <ExternalLink className="mt-1 h-3.5 w-3.5 shrink-0" />
        <span className="line-clamp-2">{article.title}</span>
      </a>
      <p className="mt-1 text-[10px] text-zinc-600">
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
      <div className="border-b border-white/[0.06] px-4 py-3">
        <h2 className="text-sm font-medium text-zinc-300">
          参考稿（扩搜 / 聚类关联）
        </h2>
        <p className="mt-0.5 text-[11px] text-zinc-600">
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
                className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[10px] text-zinc-500">
                    {a.sourceKind === "expansion" ? "扩搜" : "聚类关联"}
                  </span>
                  <span
                    className={cn(
                      "text-[11px] font-medium tabular-nums",
                      pct >= 75
                        ? "text-emerald-400"
                        : pct >= 55
                          ? "text-amber-400"
                          : "text-zinc-500",
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
                  className="mt-2 inline-flex items-start gap-1.5 text-sm leading-snug text-sky-400 hover:text-sky-300 hover:underline"
                >
                  <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {a.title}
                </a>
                <p className="mt-1 text-[10px] text-zinc-600">
                  {a.sourceHost}
                  {a.publishedAt ? ` · ${formatDate(a.publishedAt)}` : ""}
                </p>
                {a.excerpt ? (
                  <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-zinc-500">
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
    return <p className="text-sm text-zinc-500">暂无通稿正文</p>;
  }

  return (
    <article className="whitespace-pre-wrap text-sm leading-[1.85] text-zinc-200">
      {segments.map((seg, i) => (
        <span key={seg.index}>
          {seg.text}
          {seg.sources.length > 0 && (
            <button
              type="button"
              onClick={() =>
                onRefClick(`第 ${seg.index + 1} 段参考`, seg.sources)
              }
              className="mx-0.5 inline align-baseline text-[11px] font-medium text-sky-400 hover:text-sky-300"
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
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-white/[0.08] bg-[#0c0c0e] shadow-2xl transition-transform duration-200",
          open ? "translate-x-0" : "translate-x-full",
        )}
        aria-hidden={!open}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-4">
          <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-zinc-500 hover:bg-white/[0.06] hover:text-zinc-300"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {sources.length === 0 ? (
            <p className="text-sm text-zinc-500">暂无引用来源</p>
          ) : (
            <ul className="space-y-4">
              {sources.map((a) => (
                <li
                  key={a.id}
                  className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-3"
                >
                  <span className="text-[10px] text-zinc-600">
                    {a.sourceKind === "seed"
                      ? "溯源主稿"
                      : a.sourceKind === "expansion"
                        ? "扩搜参考"
                        : "聚类关联"}
                  </span>
                  {(a.similarity ?? 0) > 0 && (
                    <span className="ml-2 text-[10px] text-zinc-500">
                      相似度 {similarityPercent(a.similarity)}%
                    </span>
                  )}
                  <a
                    href={articleHref(a.url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block text-sm leading-snug text-sky-400 hover:text-sky-300 hover:underline"
                  >
                    {a.title}
                  </a>
                  <p className="mt-1 text-[10px] text-zinc-600">{a.sourceHost}</p>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
