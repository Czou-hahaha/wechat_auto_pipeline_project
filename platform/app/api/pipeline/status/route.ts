import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { PipelineRunStatus } from "@/types/pipeline";

const IDLE: PipelineRunStatus = {
  state: "idle",
  message: "BFF 未连接。请先启动 V3 BFF，再手动触发采集。",
  startedAt: "",
  finishedAt: "",
  exitCode: null,
  pid: null,
  logTail: "",
  stats: {},
};

export async function GET() {
  const bff = await fetchBff<PipelineRunStatus>("/api/pipeline/status");
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(IDLE);
}
