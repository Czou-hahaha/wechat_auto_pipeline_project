"use client";

import { useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { CardStatic } from "@/components/ui/card";
import {
  ingestModeBadge,
  type DataSourceRecord,
  type SourceIntakeProbeResult,
} from "@/types/config";

export function SourceIntakeWizard({ onSaved }: { onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const [domain, setDomain] = useState("");
  const [probing, setProbing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState<SourceIntakeProbeResult | null>(null);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function probe() {
    if (!url.trim()) return;
    setProbing(true);
    setMsg(null);
    setResult(null);
    try {
      const res = await fetch("/api/sources/intake/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url.trim(), domain: domain.trim() }),
      });
      const body = (await res.json()) as SourceIntakeProbeResult & { detail?: string };
      if (!res.ok) throw new Error(body.detail || "探测失败");
      setResult(body);
      if (body.domain && !domain) setDomain(body.domain);
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "探测失败" });
    } finally {
      setProbing(false);
    }
  }

  async function saveDraft() {
    if (!result?.draftSource) return;
    setSaving(true);
    setMsg(null);
    try {
      const res = await fetch("/api/sources/intake/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          draftSource: result.draftSource,
          draftBrowserZh: result.draftBrowserZh,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error((body as { detail?: string }).detail || "保存失败");
      setMsg({ ok: true, text: "数据源已写入配置" });
      setUrl("");
      setResult(null);
      onSaved();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "保存失败" });
    } finally {
      setSaving(false);
    }
  }

  const mode = result?.recommendedMode;
  const badge = ingestModeBadge(mode);

  return (
    <CardStatic className="mb-4 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-violet-600" />
        <h2 className="text-sm font-medium text-zinc-800">数据源接入向导</h2>
      </div>
      <p className="mb-3 text-xs text-zinc-600">
        输入 RSS / 栏目页 / 搜索页 URL，自动探测 ingest_mode（RSS · 栏目 · 搜索）并一键保存。
      </p>
      <div className="flex flex-wrap gap-2">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/feed 或栏目列表 URL"
          className="input-field min-w-[280px] flex-1 text-sm"
        />
        <input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="域名（可选）"
          className="input-field w-40 text-sm"
        />
        <button
          type="button"
          onClick={probe}
          disabled={probing || !url.trim()}
          className="inline-flex items-center gap-1 rounded-lg bg-violet-600 px-4 py-2 text-sm text-white hover:bg-violet-500 disabled:opacity-50"
        >
          {probing ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          探测
        </button>
      </div>

      {result ? (
        <div className="mt-4 space-y-2 rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-zinc-700">推荐模式</span>
            <Badge variant="muted" className={badge.className}>
              {badge.label}
            </Badge>
            {mode ? (
              <span className="font-mono text-xs text-zinc-500">{mode}</span>
            ) : null}
          </div>
          {(result.missingFields || []).length > 0 ? (
            <p className="text-xs text-amber-800">
              待补字段：{(result.missingFields || []).join("、")}
            </p>
          ) : null}
          {result.draftSource ? (
            <p className="text-xs text-zinc-600">
              草稿：{(result.draftSource as DataSourceRecord).name} ·{" "}
              {(result.draftSource as DataSourceRecord).value}
            </p>
          ) : null}
          <button
            type="button"
            onClick={saveDraft}
            disabled={saving || !result.draftSource}
            className="rounded-lg bg-sky-500 px-4 py-2 text-xs text-white hover:bg-sky-400 disabled:opacity-50"
          >
            {saving ? "保存中…" : "一键保存到配置"}
          </button>
        </div>
      ) : null}

      {msg ? (
        <p className={`mt-2 text-xs ${msg.ok ? "text-emerald-700" : "text-rose-700"}`}>
          {msg.text}
        </p>
      ) : null}
    </CardStatic>
  );
}
