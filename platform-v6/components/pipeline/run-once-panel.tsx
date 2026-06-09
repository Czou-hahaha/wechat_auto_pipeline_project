"use client";

import { useEffect } from "react";
import { Loader2, Play, RefreshCw } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { usePipelineStatus, useStartPipelineRun } from "@/hooks/use-pipeline";

export function RunOncePanel({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient();
  const { data: status, isLoading } = usePipelineStatus();
  const start = useStartPipelineRun();

  const state = status?.state ?? "idle";
  const running = state === "running" || start.isPending;

  useEffect(() => {
    if (state === "completed") {
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["qa"] });
    }
  }, [state, qc]);

  async function handleStart() {
    try {
      await start.mutateAsync();
    } catch (e) {
      const msg = e instanceof Error ? e.message : "";
      if (msg.includes("already_running") || msg.includes("409")) return;
    }
  }

  const statusTone =
    state === "running"
      ? "text-sky-600"
      : state === "completed"
        ? "text-emerald-600"
        : state === "failed"
          ? "text-rose-600"
          : "text-zinc-700";

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-3",
        compact ? "" : "rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3",
      )}
    >
      <button
        type="button"
        onClick={handleStart}
        disabled={running}
        className={cn(
          "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors",
          running
            ? "cursor-wait bg-zinc-200 text-zinc-700"
            : "bg-sky-500 text-white hover:bg-sky-400",
        )}
      >
        {running ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" />
        )}
        {running ? "采集中…" : "开始采集搜索"}
      </button>

      {!isLoading && status?.message ? (
        <p className={cn("min-w-0 flex-1 text-xs leading-relaxed", statusTone)}>
          {status.message}
        </p>
      ) : null}

      {start.isError ? (
        <p className="text-xs text-rose-700">暂时无法启动采集，请稍后重试</p>
      ) : null}

      {!compact && state === "completed" ? (
        <button
          type="button"
          onClick={() => {
            qc.invalidateQueries({ queryKey: ["dashboard"] });
            qc.invalidateQueries({ queryKey: ["events"] });
          }}
          className="inline-flex items-center gap-1 text-xs text-zinc-700 hover:text-zinc-800"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          刷新列表
        </button>
      ) : null}
    </div>
  );
}
