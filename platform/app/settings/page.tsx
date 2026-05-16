"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Database, Tags, Save, Plus, Trash2, Info, Clock } from "lucide-react";
import { CardStatic } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  KEYWORD_SECTIONS,
  type DataSourceRecord,
  type KeywordsConfig,
} from "@/types/config";
import type { ScheduleConfig } from "@/types/schedule";

type Tab = "sources" | "keywords" | "schedule";

const TIMEZONE_OPTIONS = [
  "Asia/Shanghai",
  "Asia/Hong_Kong",
  "Asia/Tokyo",
  "UTC",
  "America/New_York",
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("sources");
  const [sources, setSources] = useState<DataSourceRecord[]>([]);
  const [keywords, setKeywords] = useState<KeywordsConfig>({});
  const [schedule, setSchedule] = useState<ScheduleConfig | null>(null);
  const [configPath, setConfigPath] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: "ok" | "err"; text: string } | null>(null);

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
      setSources(ds.items || []);
      setKeywords(kw.data || {});
      setSchedule(sch as ScheduleConfig);
      setConfigPath(ds.path || kw.path || sch.env_path || "");
    } catch {
      setMessage({ type: "err", text: "加载配置失败" });
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
            morning_hour: schedule.morning_hour,
            evening_hour: schedule.evening_hour,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "保存失败");
        setSchedule(data as ScheduleConfig);
        setMessage({
          type: "ok",
          text: "定时配置已写入 V3/.env。请重启 run-scheduler 后生效。",
        });
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

  function updateSource(index: number, patch: Partial<DataSourceRecord>) {
    setSources((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  }

  function addSource() {
    setSources((prev) => [
      ...prev,
      {
        id: `src_${Date.now()}`,
        name: "新数据源",
        kind: "web",
        value: "example.com",
        ingest_mode: "html_list",
        list_monitor_url: "",
        region: "CN",
        language: "zh",
        importance_score: 50,
        tags: [],
      },
    ]);
  }

  function removeSource(index: number) {
    setSources((prev) => prev.filter((_, i) => i !== index));
  }

  function setKeywordList(key: string, text: string) {
    const list = text
      .split(/[,，\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    setKeywords((prev) => ({ ...prev, [key]: list }));
  }

  return (
    <motion.div className="mx-auto max-w-5xl space-y-6">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-semibold text-gradient-subtle">采集配置</h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-zinc-500">
          管理入库前的检索范围与<strong className="text-zinc-400">定时采集</strong>。
          数据源 / 关键词影响每次 run-once 抓什么；定时任务决定每天自动跑几次。
        </p>
      </motion.div>

      <CardStatic className="flex gap-2 border-sky-500/10 bg-sky-500/5">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-400" />
        <div className="text-xs text-zinc-400 leading-relaxed">
          <p>
            <strong className="text-zinc-300">保存</strong>需启动 BFF：
            <code className="mx-1 rounded bg-black/30 px-1">
              cd V3 && PYTHONPATH=. python -m src.main run-bff
            </code>
          </p>
          <p className="mt-1">
            数据源/关键词 → <code className="text-zinc-500">config/*.json</code>
            ；定时 → <code className="text-zinc-500">V3/.env</code> 中 SCHEDULE_*
          </p>
          <p className="mt-1">
            常驻调度：<code className="text-zinc-500">python -m src.main run-scheduler</code>
          </p>
        </div>
      </CardStatic>

      <div className="flex flex-wrap gap-2">
        <TabButton active={tab === "sources"} onClick={() => setTab("sources")} icon={Database}>
          数据源
        </TabButton>
        <TabButton active={tab === "keywords"} onClick={() => setTab("keywords")} icon={Tags}>
          关键词
        </TabButton>
        <TabButton active={tab === "schedule"} onClick={() => setTab("schedule")} icon={Clock}>
          定时任务
        </TabButton>
        <button
          type="button"
          onClick={save}
          disabled={saving || loading}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-sky-500/20 px-4 py-2 text-sm text-sky-300 hover:bg-sky-500/30 disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {saving ? "保存中…" : "保存"}
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
        <SourcesEditor
          sources={sources}
          onUpdate={updateSource}
          onAdd={addSource}
          onRemove={removeSource}
        />
      ) : tab === "keywords" ? (
        <KeywordsEditor keywords={keywords} onChange={setKeywordList} />
      ) : schedule ? (
        <ScheduleEditor schedule={schedule} onChange={setSchedule} />
      ) : null}
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

function ScheduleEditor({
  schedule,
  onChange,
}: {
  schedule: ScheduleConfig;
  onChange: (s: ScheduleConfig) => void;
}) {
  const patch = (p: Partial<ScheduleConfig>) => {
    const next = { ...schedule, ...p };
    const mh = next.morning_hour;
    const eh = next.evening_hour;
    const tz = next.timezone;
    onChange({
      ...next,
      morning_time: `${String(mh).padStart(2, "0")}:00`,
      evening_time: `${String(eh).padStart(2, "0")}:00`,
      summary: `每日 ${String(mh).padStart(2, "0")}:00、${String(eh).padStart(2, "0")}:00（${tz}）各执行一次 run-once`,
    });
  };

  return (
    <div className="space-y-4">
      <CardStatic>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-zinc-200">启用定时采集</h3>
            <p className="mt-1 text-xs text-zinc-500">
              对应 <code>SCHEDULE_ENABLED</code>；需单独运行 run-scheduler 进程
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

      <CardStatic className="space-y-4">
        <p className="text-sm text-sky-300/90">{schedule.summary}</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="早间 run-once（整点）">
            <select
              value={schedule.morning_hour}
              onChange={(e) =>
                patch({ morning_hour: Number(e.target.value) })
              }
              className="input-field"
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-zinc-600">SCHEDULE_MORNING_HOUR</p>
          </Field>
          <Field label="晚间 run-once（整点）">
            <select
              value={schedule.evening_hour}
              onChange={(e) =>
                patch({ evening_hour: Number(e.target.value) })
              }
              className="input-field"
            >
              {HOURS.map((h) => (
                <option key={h} value={h}>
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
            <p className="mt-1 text-[10px] text-zinc-600">SCHEDULE_EVENING_HOUR</p>
          </Field>
        </div>
        <Field label="时区">
          <select
            value={schedule.timezone}
            onChange={(e) => patch({ timezone: e.target.value })}
            className="input-field"
          >
            {TIMEZONE_OPTIONS.map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[10px] text-zinc-600">SCHEDULE_TIMEZONE</p>
        </Field>
      </CardStatic>

      <CardStatic className="text-xs text-zinc-500 leading-relaxed">
        <p className="font-medium text-zinc-400">说明</p>
        <ul className="mt-2 list-inside list-disc space-y-1">
          <li>
            V3 每天在<strong>两个整点</strong>各触发一次完整流水线（检索 → 聚类 → 通稿 → QA）。
          </li>
          <li>修改时间点并保存后，需重启 <code>run-scheduler</code> 才会按新时间触发。</li>
          <li>
            手动单次执行不受此影响：<code>python -m src.main run-once</code>
          </li>
        </ul>
        {schedule.restart_hint && (
          <p className="mt-2 text-amber-400/90">{schedule.restart_hint}</p>
        )}
      </CardStatic>
    </div>
  );
}

function SourcesEditor({
  sources,
  onUpdate,
  onAdd,
  onRemove,
}: {
  sources: DataSourceRecord[];
  onUpdate: (i: number, p: Partial<DataSourceRecord>) => void;
  onAdd: () => void;
  onRemove: (i: number) => void;
}) {
  return (
    <div className="space-y-3">
      <div className="flex justify-between">
        <p className="text-sm text-zinc-500">{sources.length} 个数据源</p>
        <button
          type="button"
          onClick={onAdd}
          className="inline-flex items-center gap-1 text-xs text-sky-400"
        >
          <Plus className="h-3.5 w-3.5" />
          添加
        </button>
      </div>
      {sources.map((row, i) => (
        <CardStatic key={`${row.id}-${i}`} className="space-y-3">
          <div className="flex flex-wrap gap-3">
            <Field label="名称" className="min-w-[140px] flex-1">
              <input
                value={row.name}
                onChange={(e) => onUpdate(i, { name: e.target.value })}
                className="input-field"
              />
            </Field>
            <Field label="域名 value" className="min-w-[120px]">
              <input
                value={row.value}
                onChange={(e) => onUpdate(i, { value: e.target.value })}
                className="input-field"
              />
            </Field>
            <Field label="ingest_mode" className="w-28">
              <select
                value={row.ingest_mode || "html_list"}
                onChange={(e) => onUpdate(i, { ingest_mode: e.target.value })}
                className="input-field"
              >
                <option value="html_list">html_list</option>
                <option value="rss">rss</option>
              </select>
            </Field>
            <Field label="区域" className="w-20">
              <input
                value={row.region || ""}
                onChange={(e) => onUpdate(i, { region: e.target.value })}
                className="input-field"
              />
            </Field>
          </div>
          <Field label="栏目 URL (list_monitor_url)">
            <input
              value={row.list_monitor_url || row.rss || ""}
              onChange={(e) => onUpdate(i, { list_monitor_url: e.target.value })}
              className="input-field font-mono text-xs"
            />
          </Field>
          <div className="flex items-center justify-between">
            <div className="flex flex-wrap gap-1">
              {(row.tags || []).map((t) => (
                <Badge key={t} variant="muted">
                  {t}
                </Badge>
              ))}
            </div>
            <button
              type="button"
              onClick={() => onRemove(i)}
              className="text-zinc-600 hover:text-rose-400"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        </CardStatic>
      ))}
    </div>
  );
}

function KeywordsEditor({
  keywords,
  onChange,
}: {
  keywords: KeywordsConfig;
  onChange: (key: string, text: string) => void;
}) {
  return (
    <div className="space-y-4">
      {KEYWORD_SECTIONS.map((section) => {
        const list = keywords[section.key] || [];
        return (
          <CardStatic key={section.key}>
            <div className="mb-2">
              <h3 className="text-sm font-medium text-zinc-300">{section.label}</h3>
              <p className="text-[10px] text-zinc-600">{section.hint}</p>
            </div>
            <textarea
              value={list.join("\n")}
              onChange={(e) => onChange(section.key, e.target.value)}
              rows={Math.min(8, Math.max(3, list.length + 1))}
              placeholder="每行一个词，或用逗号分隔"
              className="input-field min-h-[72px] w-full resize-y font-mono text-xs"
            />
            <p className="mt-1 text-[10px] text-zinc-600">{list.length} 条</p>
          </CardStatic>
        );
      })}
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
      <span className="mb-1 block text-[10px] uppercase tracking-wider text-zinc-600">
        {label}
      </span>
      {children}
    </label>
  );
}
