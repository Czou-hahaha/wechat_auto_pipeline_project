import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { PipelineRunStatus } from "@/types/pipeline";

const IDLE: PipelineRunStatus = {
  state: "idle",
  message: "BFF 未连接。请运行 cd platform-v6 && npm run dev（自动启动 V6 BFF :8788）。",
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
