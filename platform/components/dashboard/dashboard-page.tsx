"use client";

import { motion } from "framer-motion";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import Link from "next/link";
import { useDashboard } from "@/hooks/use-events";
import { CardStatic } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ImportanceBadge } from "@/components/events/importance-badge";
import { textPageDesc } from "@/lib/content-text";
import { RunOncePanel } from "@/components/pipeline/run-once-panel";

const PIE_COLORS = ["#38bdf8", "#6366f1"];

export function DashboardPage() {
  const { data, isLoading, isError, error } = useDashboard();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <RunOncePanel />
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-6 text-sm text-red-800">
          <p className="font-medium">Dashboard 数据加载失败</p>
          <p className="mt-1 text-red-700">
            {error instanceof Error ? error.message : "请确认 BFF 已在 :8787 运行"}
          </p>
        </div>
      </div>
    );
  }

  const regionData = [
    { name: "国内", value: data.regionSplit.domestic },
    { name: "国际", value: data.regionSplit.international },
  ];

  const hotKwMaxLen = Math.max(
    4,
    ...data.hotKeywords.map((k) => (k.keyword || "").length),
  );
  const hotKwAxisWidth = Math.min(200, Math.max(96, hotKwMaxLen * 11));

  return (
    <div className="space-y-6">
      <RunOncePanel />

      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">Dashboard</h1>
        <p className={`mt-1 ${textPageDesc}`}>低空经济事件情报总览</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[
          { label: "今日新增事件", value: data.todayNewEvents },
          { label: "QA 平均分", value: data.avgQaScore },
          { label: "AI Rewrite 次数", value: data.aiRewriteCount },
          { label: "事件总数", value: data.totalEvents },
        ].map((stat, i) => (
          <motion.div
            key={stat.label}
            initial={false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <CardStatic>
              <p className="text-xs text-zinc-700">{stat.label}</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-zinc-900">
                {stat.value}
              </p>
            </CardStatic>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <CardStatic className="lg:col-span-2">
          <h2 className="mb-4 text-sm font-medium text-zinc-700">
            关键词热度（近 7 日 · 来自事件库）
          </h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.topicTrend}>
                <defs>
                  <linearGradient id="kw-main" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" stroke="#a1a1aa" fontSize={10} />
                <YAxis stroke="#a1a1aa" fontSize={10} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    background: "#ffffff",
                    border: "1px solid rgba(0,0,0,0.08)",
                    borderRadius: 8,
                    color: "#18181b",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="低空经济"
                  stroke="#38bdf8"
                  fill="url(#kw-main)"
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="无人机"
                  stroke="#a78bfa"
                  fill="transparent"
                  strokeWidth={1.5}
                />
                <Area
                  type="monotone"
                  dataKey="eVTOL"
                  stroke="#34d399"
                  fill="transparent"
                  strokeWidth={1.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardStatic>

        <CardStatic>
          <h2 className="mb-4 text-sm font-medium text-zinc-700">国内 / 国际占比</h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={regionData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={70}
                  paddingAngle={4}
                >
                  {regionData.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </CardStatic>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <CardStatic>
          <h2 className="mb-4 text-sm font-medium text-zinc-700">热门主题词</h2>
          <p className="mb-3 text-[11px] text-zinc-700">
            统计采集配置中的检索词在事件标题/摘要中的命中次数
          </p>
          {data.hotKeywords.length === 0 ? (
            <p className="text-xs text-zinc-700">
              暂无命中，请先采集事件或检查采集配置中的主题词
            </p>
          ) : (
            <>
              <ul className="mb-3 flex flex-wrap gap-2">
                {data.hotKeywords.map((k) => (
                  <li
                    key={k.keyword}
                    className="inline-flex items-center gap-1.5 rounded-full border border-sky-500/25 bg-sky-500/10 px-3 py-1 text-xs text-sky-700"
                  >
                    <span>{k.keyword}</span>
                    <span className="tabular-nums text-sky-700">{k.count}</span>
                  </li>
                ))}
              </ul>
              <div className="h-40 min-h-[10rem] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={data.hotKeywords}
                    layout="vertical"
                    margin={{ left: 4, right: 12, top: 4, bottom: 4 }}
                  >
                    <XAxis type="number" stroke="#a1a1aa" fontSize={10} />
                    <YAxis
                      type="category"
                      dataKey="keyword"
                      stroke="#a1a1aa"
                      fontSize={10}
                      width={hotKwAxisWidth}
                      interval={0}
                      tick={{ fill: "#52525b" }}
                    />
                    <Tooltip
                      formatter={(value: number) => [value, "出现次数"]}
                      labelFormatter={(label) => String(label)}
                    />
                    <Bar
                      dataKey="count"
                      fill="#38bdf8"
                      radius={[0, 4, 4, 0]}
                      minPointSize={8}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </CardStatic>

        <CardStatic>
          <h2 className="mb-4 text-sm font-medium text-zinc-700">高重要性事件</h2>
          <ul className="space-y-3">
            {data.highImportanceEvents.map((ev) => (
              <li key={ev.id}>
                <Link
                  href={`/events/${ev.id}`}
                  className="flex items-center justify-between gap-2 rounded-lg border border-white/[0.04] px-3 py-2 hover:bg-white/[0.03]"
                >
                  <span className="text-sm text-zinc-700 line-clamp-1">{ev.title}</span>
                  <ImportanceBadge score={ev.importance_score} />
                </Link>
              </li>
            ))}
          </ul>
        </CardStatic>
      </div>
    </div>
  );
}
