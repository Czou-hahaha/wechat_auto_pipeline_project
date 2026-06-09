"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import { ExternalLink, GitBranch, Network, RotateCw } from "lucide-react";
import { CardStatic } from "@/components/ui/card";
import { cn, formatDate } from "@/lib/utils";
import type { EventIntelligenceGraphPayload, EventMapNode } from "@/types/event";

function truncateLabel(label: string, max = 28): string {
  const s = (label || "").trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

function layoutNodes(nodes: EventMapNode[], width: number, height: number) {
  const event =
    nodes.find((n) => n.isCurrent) || nodes.find((n) => n.type === "event") || nodes[0];
  const others = nodes.filter((n) => n.id !== event?.id);
  const cx = width / 2;
  const cy = height / 2;
  const positions: Record<string, { x: number; y: number }> = {};
  if (event) positions[event.id] = { x: cx, y: cy };
  const r = Math.min(width, height) * 0.34;
  others.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / Math.max(others.length, 1);
    positions[n.id] = {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    };
  });
  return positions;
}

function MiniGraph({
  nodes,
  edges,
  currentEventId,
}: {
  nodes: EventMapNode[];
  edges: { source: string; target: string; relation?: string; relationLabel?: string }[];
  currentEventId?: string;
}) {
  const router = useRouter();
  const w = 480;
  const h = 280;
  const eventNodes = useMemo(
    () => nodes.filter((n) => n.type === "event"),
    [nodes],
  );
  const eventEdges = useMemo(
    () =>
      edges.filter(
        (e) => e.source.startsWith("event:") && e.target.startsWith("event:"),
      ),
    [edges],
  );
  const pos = useMemo(() => layoutNodes(eventNodes, w, h), [eventNodes]);

  if (!eventNodes.length) {
    return <p className="text-xs text-zinc-600">暂无关联事件（仅展示与当前事件有语义/主题关联的其他事件）</p>;
  }

  const relatedCount = eventNodes.filter((n) => !n.isCurrent).length;

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${w} ${h}`} className="h-72 w-full rounded-lg bg-zinc-50">
        {eventEdges.map((e, i) => {
          const a = pos[e.source];
          const b = pos[e.target];
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2;
          return (
            <g key={`${e.source}-${e.target}-${i}`}>
              <line
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="#cbd5e1"
                strokeWidth={1.2}
              />
              {e.relationLabel ? (
                <text
                  x={mx}
                  y={my - 6}
                  textAnchor="middle"
                  fontSize={9}
                  fill="#71717a"
                >
                  {e.relationLabel}
                </text>
              ) : null}
            </g>
          );
        })}
        {eventNodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const r = n.isCurrent ? 26 : 20;
          const fill = n.isCurrent ? "#0ea5e9" : "#38bdf8";
          const label = truncateLabel(n.label || n.id, 22);
          const eventId =
            n.eventId || (n.id.startsWith("event:") ? n.id.slice(6) : "");
          const clickable = Boolean(eventId && !n.isCurrent);

          const go = () => {
            if (clickable) router.push(`/events/${eventId}`);
          };

          return (
            <g
              key={n.id}
              className={clickable ? "cursor-pointer" : ""}
              onClick={go}
              onKeyDown={(ev) => {
                if (clickable && (ev.key === "Enter" || ev.key === " ")) {
                  ev.preventDefault();
                  go();
                }
              }}
              role={clickable ? "link" : undefined}
              tabIndex={clickable ? 0 : undefined}
            >
              <circle
                cx={p.x}
                cy={p.y}
                r={r}
                fill={fill}
                opacity={0.92}
                stroke={n.isCurrent ? "#0284c7" : "#0ea5e9"}
                strokeWidth={n.isCurrent ? 2 : 1}
              />
              <title>{n.label || n.id}</title>
              <text
                x={p.x}
                y={p.y + r + 14}
                textAnchor="middle"
                fontSize={10}
                fill="#3f3f46"
                pointerEvents="none"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-2 text-[11px] text-zinc-500">
        中心为当前事件；{relatedCount > 0 ? "点击浅蓝节点可跳转关联事件" : "暂无其他关联事件"}
      </p>
      {relatedCount > 0 ? (
        <ul className="mt-1 space-y-1 text-xs text-zinc-700">
          {eventNodes
            .filter((n) => !n.isCurrent && n.eventId)
            .map((n) => (
              <li key={n.id}>
                <Link
                  href={`/events/${n.eventId}`}
                  className="text-sky-700 hover:underline"
                >
                  {n.label}
                </Link>
              </li>
            ))}
        </ul>
      ) : null}
    </div>
  );
}

export function EventIntelligenceGraphPanel({
  data,
  loading,
  onRefreshMemory,
  refreshing,
}: {
  data: EventIntelligenceGraphPayload | null;
  loading: boolean;
  onRefreshMemory?: () => void;
  refreshing?: boolean;
}) {
  if (loading) {
    return (
      <CardStatic className="p-4">
        <p className="text-xs text-zinc-600">加载事件图谱…</p>
      </CardStatic>
    );
  }
  if (!data) {
    return (
      <CardStatic className="p-4">
        <p className="text-xs text-zinc-600">暂无事件图谱数据</p>
      </CardStatic>
    );
  }

  const graph = data.eventGraph || data.visualization;
  const vizNodes = graph?.nodes || [];
  const vizEdges = graph?.edges || [];

  return (
    <div className="space-y-4">
      <CardStatic className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <Network className="h-4 w-4 text-sky-600" />
          <h3 className="text-sm font-medium text-zinc-800">事件关联图谱</h3>
        </div>
        <MiniGraph
          nodes={vizNodes}
          edges={vizEdges}
          currentEventId={data.eventId}
        />
        <p className="mt-2 text-[11px] text-zinc-600">
          本体：事件 · 节点 {vizNodes.filter((n) => n.type === "event").length}（含当前）·
          关联边 {vizEdges.filter((e) => e.source?.startsWith("event:")).length}
          {data.graph?.evolutionKind ? ` · 记忆演化 ${data.graph.evolutionKind}` : ""}
        </p>
      </CardStatic>

      <CardStatic className="p-4">
        <div className="mb-3 flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-zinc-700" />
          <h3 className="text-sm font-medium text-zinc-800">时间轴与关联链</h3>
        </div>
        {(data.graph?.timeline || []).length > 0 ? (
          <ul className="mb-3 space-y-1 text-xs text-zinc-700">
            {data.graph!.timeline!.map((t, i) => (
              <li key={`${t.date}-${i}`} className="flex gap-2">
                <span className="shrink-0 tabular-nums text-zinc-500">
                  {(t.date || "").slice(0, 10)}
                </span>
                <span>{t.update || t.kind}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {data.history?.chain?.length ? (
          <ul className="space-y-1 text-xs">
            {data.history.chain.map((node) => (
              <li key={node.eventId} className="flex items-center gap-2">
                <span className="tabular-nums text-[10px] text-zinc-500">
                  {node.createdAt ? node.createdAt.slice(0, 10) : "—"}
                </span>
                {node.relation === "current" ? (
                  <span className="font-medium text-sky-700">{node.title}</span>
                ) : (
                  <Link
                    href={`/events/${node.eventId}`}
                    className="text-zinc-700 hover:text-sky-700 hover:underline"
                  >
                    {node.title}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-zinc-600">暂无关联事件链</p>
        )}
        {data.history?.timelineReport ? (
          <p className="mt-3 whitespace-pre-wrap text-xs leading-relaxed text-zinc-700">
            {data.history.timelineReport}
          </p>
        ) : null}
      </CardStatic>

      <CardStatic className="p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-zinc-800">记忆摘要</h3>
          {onRefreshMemory ? (
            <button
              type="button"
              onClick={onRefreshMemory}
              disabled={refreshing}
              className="inline-flex items-center gap-1 rounded-md border border-zinc-200 px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-50 disabled:opacity-50"
            >
              <RotateCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
              刷新
            </button>
          ) : null}
        </div>
        <p className="text-xs text-zinc-700">
          QA {data.memory?.qaScore ?? "—"}
          {data.memory?.updatedAt
            ? ` · 更新 ${formatDate(data.memory.updatedAt)}`
            : ""}
        </p>
        <ul className="mt-2 space-y-1 text-xs text-zinc-600">
          {(data.memory?.facts || []).map((f, i) => (
            <li key={`${f.title}-${i}`} className="line-clamp-1">
              {f.title}
            </li>
          ))}
        </ul>
      </CardStatic>

      {(data.map?.evidence || []).length > 0 ? (
        <CardStatic className="p-4">
          <h3 className="mb-2 text-sm font-medium text-zinc-800">证据片段</h3>
          <ul className="space-y-2 text-xs text-zinc-700">
            {data.map!.evidence!.map((ev, idx) => (
              <li key={`${ev.url}-${idx}`}>
                <a
                  href={ev.url.startsWith("http") ? ev.url : `https://${ev.url}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sky-700 hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  [{ev.sourceHost}] {ev.snippet?.slice(0, 120)}
                </a>
              </li>
            ))}
          </ul>
        </CardStatic>
      ) : null}
    </div>
  );
}
