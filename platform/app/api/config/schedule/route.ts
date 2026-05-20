import { NextRequest, NextResponse } from "next/server";
import { MOCK_SCHEDULE } from "@/lib/mock/config";
import { fetchBff } from "@/services/bff-proxy";
import type { ScheduleConfig } from "@/types/schedule";

export async function GET() {
  const bff = await fetchBff<ScheduleConfig>("/api/config/schedule");
  const body = bff ?? MOCK_SCHEDULE;
  return NextResponse.json(body, {
    headers: { "Cache-Control": "no-store, max-age=0" },
  });
}

export async function PUT(req: NextRequest) {
  const body = await req.json();
  const bff = await fetchBff<ScheduleConfig>("/api/config/schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(
    { error: "BFF unavailable — 请启动 V3 run-bff 以写入 .env" },
    { status: 503 },
  );
}
