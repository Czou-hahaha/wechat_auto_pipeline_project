"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Database, Tags, Save, Plus, Pencil, Trash2, Clock, X } from "lucide-react";
import { CardStatic } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  KEYWORD_SECTIONS,
  languageLabel,
  type DataSourceRecord,
  type KeywordsConfig,
} from "@/types/config";
import type { ScheduleConfig, ScheduleJob } from "@/types/schedule";
import { newScheduleJob } from "@/types/schedule";

type Tab = "sources" | "keywords" | "schedule";

const TIMEZONE_OPTIONS = [
  "Asia/Shanghai",
  "Asia/Hong_Kong",
  "Asia/Tokyo",
  "UTC",
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const MINUTES = Array.from({ length: 60 }, (_, i) => i);

const EMPTY_SOURCE: DataSourceRecord = {
  id: "",
  name: "",
  kind: "web",
  value: "",
  language: "zh",
  ingest_mode: "html_list",
  list_monitor_url: "",
  region: "CN",
};

function ingestModeLabel(mode?: string): string {
  return mode === "rss" ? "RSS" : "栏目页";
}

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("sources");
  const [sources, setSources] = useState<DataSourceRecord[]>([]);
  const [keywords, setKeywords] = useState<KeywordsConfig>({});
  const [schedule, setSchedule] = useState<ScheduleConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [scheduleFeedback, setScheduleFeedback] = useState<{
    type: "ok" | "err";
    text: string;
  } | null>(null);
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<DataSourceRecord | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const [dsRes, kwRes, schRes] = await Promise.all([
        fetch("/api/config/data-sources"),
        fetch("/api/config/keywords"),
        fetch("/api/config/schedule"),
      ]);
      const ds = await dsRes.json();
      const kw = await kwRes.json();
      const sch = await schRes.json();
      if (!schRes.ok) {
        throw new Error(
          (sch as { error?: string }).error || `schedule HTTP ${schRes.status}`,
        );
      }
      setSources(ds.items || []);
      const rawKw = (kw.data || {}) as KeywordsConfig;
      setKeywords({
        chinese_keywords: rawKw.chinese_keywords || [],
        english_keywords: rawKw.english_keywords || [],
      });
      const schData = sch as ScheduleConfig;
      setSchedule({
        ...schData,
        jobs: schData.jobs?.length
          ? schData.jobs
          : [
              { id: "job_morning", label: "早间采集", hour: 8, minute: 0 },
              { id: "job_evening", label: "晚间采集", hour: 20, minute: 0 },
            ],
        article_age: schData.article_age ?? {
          unit: "hours",
          value: schData.article_age_hours ?? 14,
        },
        article_age_limit_enabled: schData.article_age_limit_enabled ?? true,
        article_age_hours: schData.article_age_hours ?? 14,
      });
    } catch {
      setMessage({ type: "err", text: "加载失败，请刷新页面" });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      if (tab === "sources") {
        const res = await fetch("/api/config/data-sources", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(sources),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        setSources(data.items || sources);
        setMessage({ type: "ok", text: "数据源已保存" });
      } else if (tab === "keywords") {
        const res = await fetch("/api/config/keywords", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(keywords),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        setKeywords(data.data || keywords);
        setMessage({ type: "ok", text: "关键词已保存" });
      } else if (tab === "schedule" && schedule) {
        const res = await fetch("/api/config/schedule", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            enabled: schedule.enabled,
            timezone: schedule.timezone,
            jobs: schedule.jobs,
            article_age: schedule.article_age,
            article_age_limit_enabled: schedule.article_age_limit_enabled ?? true,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        const saved = data as ScheduleConfig;
        setSchedule(saved);
        const note =
          saved.schedulerNote ||
          saved.schedulerWarning ||
          (saved.scheduler?.state === "running"
            ? "定时调度已在后台运行"
            : "定时与采集窗口已保存");
        setScheduleFeedback({
          type: saved.schedulerWarning ? "err" : "ok",
          text: note,
        });
        setMessage(null);
      }
    } catch (e) {
      setMessage({
        type: "err",
        text: e instanceof Error ? e.message : "保存失败",
      });
    } finally {
      setSaving(false);
    }
  }

  function openAdd() {
    setDraft({
      ...EMPTY_SOURCE,
      id: `src_${Date.now()}`,
      name: "新数据源",
    });
    setEditIndex(-1);
  }

  function openEdit(index: number) {
    setDraft({ ...sources[index] });
    setEditIndex(index);
  }

  function commitDraft() {
    if (!draft || editIndex === null) return;
    if (editIndex < 0) {
      setSources((prev) => [...prev, draft]);
    } else {
      setSources((prev) =>
        prev.map((row, i) => (i === editIndex ? draft : row)),
      );
    }
    setEditIndex(null);
    setDraft(null);
  }

  function removeSource(index: number) {
    if (!confirm(`确定删除「${sources[index]?.name}」？`)) return;
    setSources((prev) => prev.filter((_, i) => i !== index));
  }

  function setKeywordList(key: keyof KeywordsConfig, text: string) {
    const list = text
      .split(/[,，\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    setKeywords((prev) => ({ ...prev, [key]: list }));
  }

  return (
    <motion.div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gradient-subtle">采集配置</h1>
        <p className="mt-1 text-sm text-zinc-500">
          配置数据源、检索词与定时策略；保存后点击「开始采集搜索」即按此配置入库。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <TabButton active={tab === "sources"} onClick={() => setTab("sources")} icon={Database}>
          数据源
        </TabButton>
        <TabButton active={tab === "keywords"} onClick={() => setTab("keywords")} icon={Tags}>
          关键词
        </TabButton>
        <TabButton
          active={tab === "schedule"}
          onClick={() => {
            setTab("schedule");
            setMessage(null);
          }}
          icon={Clock}
        >
          定时任务
        </TabButton>
        <button
          type="button"
          onClick={save}
          disabled={saving || loading}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-sky-500 px-4 py-2 text-sm text-white hover:bg-sky-400 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "保存中…" : "保存配置"}
        </button>
      </div>

      {message && (
        <p
          className={cn(
            "text-sm",
            message.type === "ok" ? "text-emerald-400" : "text-rose-400",
          )}
        >
          {message.text}
        </p>
      )}

      {loading ? (
        <Skeleton className="h-96" />
      ) : tab === "sources" ? (
        <SourcesTable
          sources={sources}
          onAdd={openAdd}
          onEdit={openEdit}
          onRemove={removeSource}
        />
      ) : tab === "keywords" ? (
        <KeywordsEditor keywords={keywords} onChange={setKeywordList} />
      ) : schedule ? (
        <ScheduleEditor
          schedule={schedule}
          onChange={setSchedule}
          feedback={scheduleFeedback}
        />
      ) : null}

      {draft && editIndex !== null && (
        <SourceEditModal
          draft={draft}
          onChange={setDraft}
          onClose={() => {
            setEditIndex(null);
            setDraft(null);
          }}
          onConfirm={commitDraft}
          isNew={editIndex < 0}
        />
      )}
    </motion.div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  children,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-sm transition-colors",
        active
          ? "border-sky-500/40 bg-sky-500/10 text-sky-300"
          : "border-white/[0.06] text-zinc-500 hover:text-zinc-300",
      )}
    >
      <Icon className="h-4 w-4" />
      {children}
    </button>
  );
}

function SourcesTable({
  sources,
  onAdd,
  onEdit,
  onRemove,
}: {
  sources: DataSourceRecord[];
  onAdd: () => void;
  onEdit: (i: number) => void;
  onRemove: (i: number) => void;
}) {
  return (
    <CardStatic className="overflow-hidden p-0">
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <span className="text-sm text-zinc-400">共 {sources.length} 个数据源</span>
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-1.5 rounded-lg bg-sky-500/15 px-3 py-1.5 text-xs text-sky-300 hover:bg-sky-500/25"
        >
          <Plus className="h-3.5 w-3.5" />
          添加
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/[0.06] text-[11px] uppercase tracking-wider text-zinc-600">
              <th className="px-4 py-2.5 font-medium">名称</th>
              <th className="px-4 py-2.5 font-medium">语言</th>
              <th className="px-4 py-2.5 font-medium">域名</th>
              <th className="px-4 py-2.5 font-medium">方式</th>
              <th className="px-4 py-2.5 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((row, i) => (
              <tr
                key={`${row.id}-${i}`}
                className="border-b border-white/[0.04] hover:bg-white/[0.02]"
              >
                <td className="px-4 py-3 text-zinc-200">{row.name}</td>
                <td className="px-4 py-3">
                  <Badge
                    variant="muted"
                    className={
                      (row.language || "zh").startsWith("en")
                        ? "border-violet-500/30 text-violet-300"
                        : "border-amber-500/30 text-amber-200"
                    }
                  >
                    {languageLabel(row.language)}
                  </Badge>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-zinc-500">{row.value}</td>
                <td className="px-4 py-3 text-xs text-zinc-500">
                  {ingestModeLabel(row.ingest_mode)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => onEdit(i)}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-white/[0.06] hover:text-sky-300"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                      修改
                    </button>
                    <button
                      type="button"
                      onClick={() => onRemove(i)}
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-zinc-400 hover:bg-white/[0.06] hover:text-rose-400"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sources.length === 0 && (
        <p className="px-4 py-8 text-center text-sm text-zinc-600">暂无数据源，点击添加</p>
      )}
    </CardStatic>
  );
}

function SourceEditModal({
  draft,
  onChange,
  onClose,
  onConfirm,
  isNew,
}: {
  draft: DataSourceRecord;
  onChange: (d: DataSourceRecord) => void;
  onClose: () => void;
  onConfirm: () => void;
  isNew: boolean;
}) {
  const patch = (p: Partial<DataSourceRecord>) => onChange({ ...draft, ...p });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <CardStatic className="w-full max-w-lg space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-zinc-100">
            {isNew ? "添加数据源" : "修改数据源"}
          </h3>
          <button type="button" onClick={onClose} className="text-zinc-500 hover:text-zinc-300">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="名称">
            <input
              value={draft.name}
              onChange={(e) => patch({ name: e.target.value })}
              className="input-field"
            />
          </Field>
          <Field label="语言">
            <select
              value={draft.language || "zh"}
              onChange={(e) => patch({ language: e.target.value })}
              className="input-field"
            >
              <option value="zh">中文</option>
              <option value="en">英文</option>
            </select>
          </Field>
          <Field label="域名" className="sm:col-span-2">
            <input
              value={draft.value}
              onChange={(e) => patch({ value: e.target.value })}
              className="input-field font-mono text-xs"
              placeholder="example.com"
            />
          </Field>
          <Field label="采集方式">
            <select
              value={draft.ingest_mode || "html_list"}
              onChange={(e) => patch({ ingest_mode: e.target.value })}
              className="input-field"
            >
              <option value="html_list">栏目页</option>
              <option value="rss">RSS</option>
            </select>
          </Field>
          <Field label="区域">
            <select
              value={draft.region || "CN"}
              onChange={(e) => patch({ region: e.target.value })}
              className="input-field"
            >
              <option value="CN">中国</option>
              <option value="INTL">国际</option>
            </select>
          </Field>
          <Field label="栏目 / RSS 地址" className="sm:col-span-2">
            <input
              value={draft.list_monitor_url || draft.rss || ""}
              onChange={(e) => patch({ list_monitor_url: e.target.value })}
              className="input-field font-mono text-xs"
            />
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg px-4 py-2 text-sm text-zinc-400 hover:text-zinc-200"
          >
            取消
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className="rounded-lg bg-sky-500 px-4 py-2 text-sm text-white hover:bg-sky-400"
          >
            确定
          </button>
        </div>
      </CardStatic>
    </div>
  );
}

function KeywordsEditor({
  keywords,
  onChange,
}: {
  keywords: KeywordsConfig;
  onChange: (key: keyof KeywordsConfig, text: string) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {KEYWORD_SECTIONS.map((section) => {
        const list = keywords[section.key] || [];
        return (
          <CardStatic key={section.key}>
            <h3 className="text-sm font-medium text-zinc-300">{section.label}</h3>
            <textarea
              value={list.join("\n")}
              onChange={(e) => onChange(section.key, e.target.value)}
              rows={8}
              placeholder="每行一个词"
              className="input-field mt-2 min-h-[140px] w-full resize-y font-mono text-xs"
            />
            <p className="mt-1 text-[10px] text-zinc-600">{list.length} 条</p>
          </CardStatic>
        );
      })}
    </div>
  );
}

function ScheduleJobsStatus({
  schedule,
  feedback,
}: {
  schedule: ScheduleConfig;
  feedback: { type: "ok" | "err"; text: string } | null;
}) {
  if (feedback) {
    return (
      <p
        className={cn(
          "text-xs leading-relaxed",
          feedback.type === "ok" ? "text-emerald-400/90" : "text-rose-400",
        )}
      >
        {feedback.text}
      </p>
    );
  }
  if (schedule.scheduler?.state === "running") {
    return (
      <p className="text-xs leading-relaxed text-emerald-400/90">
        调度已启动，将按下方时刻自动采集
        {schedule.scheduler.jobsSummary
          ? `（${schedule.scheduler.jobsSummary}）`
          : ""}
      </p>
    );
  }
  if (schedule.enabled) {
    return (
      <p className="text-xs text-amber-400/90">
        已启用定时采集，保存后将自动启动调度
      </p>
    );
  }
  return null;
}

function ScheduleEditor({
  schedule,
  onChange,
  feedback,
}: {
  schedule: ScheduleConfig;
  onChange: (s: ScheduleConfig) => void;
  feedback: { type: "ok" | "err"; text: string } | null;
}) {
  const patch = (p: Partial<ScheduleConfig>) => onChange({ ...schedule, ...p });

  function updateJob(index: number, job: Partial<ScheduleJob>) {
    const jobs = schedule.jobs.map((j, i) =>
      i === index ? { ...j, ...job } : j,
    );
    patch({ jobs });
  }

  function removeJob(index: number) {
    if (schedule.enabled && schedule.jobs.length <= 1) {
      alert("启用定时采集时请至少保留一个任务，或先关闭「启用定时采集」");
      return;
    }
    patch({ jobs: schedule.jobs.filter((_, i) => i !== index) });
  }

  function addJob() {
    patch({ jobs: [...schedule.jobs, newScheduleJob()] });
  }

  const ageLimitOn = schedule.article_age_limit_enabled ?? true;
  const ageUnit = schedule.article_age?.unit ?? "hours";
  const ageValue = schedule.article_age?.value ?? 14;

  return (
    <div className="space-y-4">
      <CardStatic>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-zinc-200">启用定时采集</h3>
            <p className="mt-1 text-xs text-zinc-500">
              开启并保存后，BFF 会自动启动 run-scheduler；关闭则停止后台调度
            </p>
          </div>
          <label className="relative inline-flex cursor-pointer items-center">
            <input
              type="checkbox"
              checked={schedule.enabled}
              onChange={(e) => patch({ enabled: e.target.checked })}
              className="peer sr-only"
            />
            <span className="h-6 w-11 rounded-full bg-zinc-700 peer-checked:bg-sky-600 after:absolute after:left-0.5 after:top-0.5 after:h-5 after:w-5 after:rounded-full after:bg-white after:transition peer-checked:after:translate-x-5" />
          </label>
        </div>
      </CardStatic>

      <CardStatic className="space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-sm text-zinc-400">定时任务（每日执行时刻）</span>
          <button
            type="button"
            onClick={addJob}
            className="inline-flex items-center gap-1 rounded-lg bg-sky-500/15 px-2.5 py-1 text-xs text-sky-300 hover:bg-sky-500/25"
          >
            <Plus className="h-3.5 w-3.5" />
            添加
          </button>
        </div>
        <ScheduleJobsStatus schedule={schedule} feedback={feedback} />
        {schedule.jobs.length === 0 ? (
          <p className="text-xs text-zinc-600">暂无定时点（关闭「启用定时采集」时可留空）</p>
        ) : (
          <ul className="space-y-2">
            {schedule.jobs.map((job, i) => (
              <li
                key={job.id}
                className="flex flex-wrap items-center gap-2 border-b border-white/[0.04] pb-2 last:border-0 last:pb-0"
              >
                <input
                  value={job.label}
                  onChange={(e) => updateJob(i, { label: e.target.value })}
                  className="input-field w-36 shrink-0 text-sm"
                  placeholder="名称"
                />
                <select
                  value={job.hour}
                  onChange={(e) =>
                    updateJob(i, { hour: Number(e.target.value) })
                  }
                  className="input-field w-[4.5rem] shrink-0 tabular-nums text-sm"
                  aria-label="时"
                >
                  {HOURS.map((h) => (
                    <option key={h} value={h}>
                      {String(h).padStart(2, "0")} 时
                    </option>
                  ))}
                </select>
                <select
                  value={job.minute}
                  onChange={(e) =>
                    updateJob(i, { minute: Number(e.target.value) })
                  }
                  className="input-field w-[4.5rem] shrink-0 tabular-nums text-sm"
                  aria-label="分"
                >
                  {MINUTES.map((m) => (
                    <option key={m} value={m}>
                      {String(m).padStart(2, "0")} 分
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={() => removeJob(i)}
                  className="ml-auto inline-flex shrink-0 items-center gap-1 text-xs text-zinc-500 hover:text-rose-400"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  删除
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardStatic>

      <CardStatic className="space-y-3 p-4">
        <p className="text-sm text-zinc-500">{schedule.summary}</p>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-xs text-zinc-500 shrink-0">时区</span>
          <select
            value={schedule.timezone}
            onChange={(e) => patch({ timezone: e.target.value })}
            className="input-field w-auto min-w-[10rem] max-w-full text-sm"
          >
            {TIMEZONE_OPTIONS.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
          <span className="text-xs text-zinc-500 shrink-0">采集时间范围</span>
          <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="checkbox"
              checked={ageLimitOn}
              onChange={(e) =>
                patch({ article_age_limit_enabled: e.target.checked })
              }
              className="rounded border-white/20"
            />
            限制发布时间
          </label>
          {ageLimitOn ? (
            <>
              <div className="flex shrink-0 rounded-lg border border-white/[0.06] p-0.5">
                {(["hours", "days"] as const).map((u) => (
                  <button
                    key={u}
                    type="button"
                    onClick={() =>
                      patch({
                        article_age: {
                          unit: u,
                          value: ageValue || (u === "days" ? 3 : 24),
                        },
                      })
                    }
                    className={cn(
                      "rounded-md px-2 py-1 text-xs transition-colors",
                      ageUnit === u
                        ? "bg-sky-500/20 text-sky-300"
                        : "text-zinc-500 hover:text-zinc-300",
                    )}
                  >
                    {u === "hours" ? "小时" : "天"}
                  </button>
                ))}
              </div>
              <input
                type="number"
                min={1}
                max={ageUnit === "days" ? 365 : 8760}
                value={ageValue}
                onChange={(e) =>
                  patch({
                    article_age: {
                      unit: ageUnit,
                      value: Math.max(1, Number(e.target.value) || 1),
                    },
                  })
                }
                className="input-field w-16 shrink-0 tabular-nums text-sm"
              />
              <span className="text-xs text-zinc-500">
                {ageUnit === "days" ? "天" : "小时"}
              </span>
            </>
          ) : (
            <span className="text-xs text-zinc-600">已取消，不按发布时间过滤</span>
          )}
          {ageLimitOn && (
            <button
              type="button"
              onClick={() => patch({ article_age_limit_enabled: false })}
              className="text-xs text-zinc-500 hover:text-rose-400"
            >
              取消限制
            </button>
          )}
        </div>
      </CardStatic>
    </div>
  );
}

function Field({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1 block text-xs text-zinc-500">{label}</span>
      {children}
    </label>
  );
}
