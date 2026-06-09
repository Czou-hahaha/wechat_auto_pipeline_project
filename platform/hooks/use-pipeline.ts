"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { PipelineRunStartResponse, PipelineRunStatus } from "@/types/pipeline";

async function fetchStatus(): Promise<PipelineRunStatus> {
  const res = await fetch("/api/pipeline/status");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<PipelineRunStatus>;
}

async function startRunOnce(): Promise<PipelineRunStartResponse> {
  const res = await fetch("/api/pipeline/run-once", { method: "POST" });
  const body = (await res.json()) as PipelineRunStartResponse & {
    error?: string;
    message?: string;
  };
  if (!res.ok) {
    throw new Error(
      body.message || body.error || (res.status === 409 ? "采集已在运行" : `HTTP ${res.status}`),
    );
  }
  return body;
}

export function usePipelineStatus() {
  return useQuery({
    queryKey: ["pipeline-status"],
    queryFn: fetchStatus,
    refetchInterval: (query) =>
      query.state.data?.state === "running" ? 3000 : 15_000,
  });
}

export function useStartPipelineRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: startRunOnce,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pipeline-status"] });
    },
  });
}

export function useBffHealth() {
  return useQuery({
    queryKey: ["bff-health"],
    queryFn: async () => {
      const res = await fetch("/api/health");
      if (!res.ok) return { connected: false as const };
      const data = (await res.json()) as { connected?: boolean; service?: string };
      return { connected: Boolean(data.connected), service: data.service };
    },
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
