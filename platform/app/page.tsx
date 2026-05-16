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

const PIE_COLORS = ["#38bdf8", "#6366f1"];

export default function DashboardPage() {
  const { data, isLoading } = useDashboard();

  if (isLoading || !data) {
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

  const regionData = [
    { name: "国内", value: data.regionSplit.domestic },
    { name: "国际", value: data.regionSplit.international },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-500">低空经济事件情报总览</p>
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
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <CardStatic>
              <p className="text-xs text-zinc-500">{stat.label}</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums text-zinc-100">
                {stat.value}
              </p>
            </CardStatic>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <CardStatic className="lg:col-span-2">
          <h2 className="mb-4 text-sm font-medium text-zinc-400">
            FAA / BVLOS / eVTOL 热度趋势
          </h2>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.topicTrend}>
                <defs>
                  <linearGradient id="faa" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#38bdf8" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#38bdf8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" stroke="#52525b" fontSize={10} />
                <YAxis stroke="#52525b" fontSize={10} />
                <Tooltip
                  contentStyle={{
                    background: "#18181b",
                    border: "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 8,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="FAA"
                  stroke="#38bdf8"
                  fill="url(#faa)"
                  strokeWidth={2}
                />
                <Area
                  type="monotone"
                  dataKey="BVLOS"
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
          <h2 className="mb-4 text-sm font-medium text-zinc-400">国内 / 国际占比</h2>
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
          <h2 className="mb-4 text-sm font-medium text-zinc-400">热门关键词</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.hotKeywords} layout="vertical">
                <XAxis type="number" stroke="#52525b" fontSize={10} />
                <YAxis
                  type="category"
                  dataKey="keyword"
                  stroke="#52525b"
                  fontSize={10}
                  width={72}
                />
                <Bar dataKey="count" fill="#38bdf8" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardStatic>

        <CardStatic>
          <h2 className="mb-4 text-sm font-medium text-zinc-400">高重要性事件</h2>
          <ul className="space-y-3">
            {data.highImportanceEvents.map((ev) => (
              <li key={ev.id}>
                <Link
                  href={`/events/${ev.id}`}
                  className="flex items-center justify-between gap-2 rounded-lg border border-white/[0.04] px-3 py-2 hover:bg-white/[0.03]"
                >
                  <span className="text-sm text-zinc-300 line-clamp-1">{ev.title}</span>
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
