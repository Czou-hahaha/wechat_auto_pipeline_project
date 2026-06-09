"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { MessageSquare, RefreshCw, ShieldCheck } from "lucide-react";
import { CardStatic } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { FeedbackSummaryWithPrompt } from "@/types/config";

export default function FeedbackPage() {
  const [summary, setSummary] = useState<FeedbackSummaryWithPrompt | null>(null);
  const [loading, setLoading] = useState(true);
  const [recomputing, setRecomputing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [confirmToken, setConfirmToken] = useState("");
  const [lastBackup, setLastBackup] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/feedback/summary");
      const body = (await res.json()) as FeedbackSummaryWithPrompt;
      setSummary(body);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  async function recompute() {
    setRecomputing(true);
    setMsg(null);
    try {
      const res = await fetch("/api/feedback/prompt/recompute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ windowDays: 14 }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error((body as { detail?: string }).detail || "重算失败");
      setMsg({ ok: true, text: "已生成 Prompt 建议，请预览后确认应用" });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "重算失败" });
    } finally {
      setRecomputing(false);
    }
  }

  async function applySuggestion() {
    const sid = summary?.promptSuggestion?.id;
    if (!sid) return;
    setApplying(true);
    setMsg(null);
    try {
      const res = await fetch("/api/feedback/prompt/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          suggestionId: sid,
          confirmToken: confirmToken || summary?.promptSuggestion?.requires_manual_confirm_token,
        }),
      });
      const body = (await res.json()) as { backup_path?: string; detail?: string };
      if (!res.ok) throw new Error(body.detail || "应用失败");
      if (body.backup_path) setLastBackup(body.backup_path);
      setMsg({ ok: true, text: "Prompt 规则已应用，下一轮 run-once QA 将注入新 hard/soft 规则" });
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "应用失败" });
    } finally {
      setApplying(false);
    }
  }

  async function rollback() {
    if (!lastBackup) return;
    setApplying(true);
    try {
      const res = await fetch("/api/feedback/prompt/rollback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ backupPath: lastBackup }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error((body as { detail?: string }).detail || "回滚失败");
      setMsg({ ok: true, text: "已回滚 Prompt Contract" });
      setLastBackup("");
      await load();
    } catch (e) {
      setMsg({ ok: false, text: e instanceof Error ? e.message : "回滚失败" });
    } finally {
      setApplying(false);
    }
  }

  const suggestion = summary?.promptSuggestion;
  const hardAdd =
    suggestion?.additions?.hard_rules ||
    suggestion?.diff?.hard_rules?.add ||
    [];
  const softAdd =
    suggestion?.additions?.soft_rules ||
    suggestion?.diff?.soft_rules?.add ||
    [];

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-900">反馈与策略</h1>
        <p className="mt-1 text-sm text-zinc-600">
          汇总编辑反馈 → 生成 Prompt 规则建议 → 人工确认后写入 QA/Rewrite 注入链
        </p>
      </div>

      {loading ? (
        <CardStatic className="p-6 text-sm text-zinc-600">加载中…</CardStatic>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <CardStatic>
              <p className="text-xs text-zinc-600">14 日反馈总数</p>
              <p className="mt-1 text-3xl font-semibold tabular-nums">{summary?.total ?? 0}</p>
            </CardStatic>
            <CardStatic>
              <p className="text-xs text-zinc-600">分类分布</p>
              <ul className="mt-2 space-y-1 text-xs text-zinc-700">
                {Object.entries(summary?.byCategory || {}).map(([k, v]) => (
                  <li key={k} className="flex justify-between">
                    <span>{k}</span>
                    <span className="tabular-nums">{v}</span>
                  </li>
                ))}
              </ul>
            </CardStatic>
            <CardStatic>
              <p className="text-xs text-zinc-600">最近反馈</p>
              <ul className="mt-2 max-h-24 space-y-1 overflow-y-auto text-xs text-zinc-700">
                {(summary?.latest || []).slice(0, 5).map((row, i) => (
                  <li key={i} className="line-clamp-1">
                    {row.category}: {row.note}
                  </li>
                ))}
              </ul>
            </CardStatic>
          </div>

          <CardStatic className="p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-sky-600" />
                <h2 className="text-sm font-medium text-zinc-800">Prompt 建议 diff</h2>
              </div>
              <button
                type="button"
                onClick={recompute}
                disabled={recomputing}
                className="inline-flex items-center gap-1 rounded-lg border border-zinc-200 px-3 py-1.5 text-xs hover:bg-zinc-50 disabled:opacity-50"
              >
                <RefreshCw className={cn("h-3.5 w-3.5", recomputing && "animate-spin")} />
                重算建议
              </button>
            </div>

            {!suggestion ? (
              <p className="text-sm text-zinc-600">
                暂无待应用建议。同 category 反馈 ≥2 条后点击「重算建议」。
              </p>
            ) : (
              <div className="space-y-3 text-sm">
                <ul className="text-xs text-zinc-600">
                  {(suggestion.reasons || []).map((r) => (
                    <li key={r}>· {r}</li>
                  ))}
                </ul>
                {hardAdd.length > 0 ? (
                  <div className="rounded-lg border border-rose-200 bg-rose-50/50 p-3">
                    <p className="text-xs font-medium text-rose-800">+ hard_rules</p>
                    <ul className="mt-1 space-y-1 text-xs text-rose-900">
                      {hardAdd.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {softAdd.length > 0 ? (
                  <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
                    <p className="text-xs font-medium text-amber-800">+ soft_rules</p>
                    <ul className="mt-1 space-y-1 text-xs text-amber-900">
                      {softAdd.map((r) => (
                        <li key={r}>{r}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                <div className="flex flex-wrap items-center gap-2 pt-2">
                  <input
                    value={confirmToken}
                    onChange={(e) => setConfirmToken(e.target.value)}
                    placeholder="确认 token（默认已内置）"
                    className="input-field min-w-[200px] text-xs"
                  />
                  <button
                    type="button"
                    onClick={applySuggestion}
                    disabled={applying}
                    className="rounded-lg bg-sky-500 px-4 py-2 text-xs text-white hover:bg-sky-400 disabled:opacity-50"
                  >
                    确认应用
                  </button>
                  {lastBackup ? (
                    <button
                      type="button"
                      onClick={rollback}
                      disabled={applying}
                      className="rounded-lg border border-zinc-200 px-3 py-2 text-xs hover:bg-zinc-50"
                    >
                      回滚上次
                    </button>
                  ) : null}
                </div>
              </div>
            )}
          </CardStatic>

          <CardStatic className="p-4">
            <div className="flex items-center gap-2 text-sm text-zinc-700">
              <MessageSquare className="h-4 w-4" />
              在
              <Link href="/events" className="text-sky-700 hover:underline">
                事件详情
              </Link>
              页提交带 category 的反馈，或前往
              <Link href="/settings" className="text-sky-700 hover:underline">
                采集配置
              </Link>
              调整 QA 阈值策略。
            </div>
          </CardStatic>
        </>
      )}

      {msg ? (
        <p className={cn("text-sm", msg.ok ? "text-emerald-700" : "text-rose-700")}>
          {msg.text}
        </p>
      ) : null}
    </div>
  );
}
