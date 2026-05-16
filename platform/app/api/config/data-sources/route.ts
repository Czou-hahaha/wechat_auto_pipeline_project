import { NextRequest, NextResponse } from "next/server";
import { MOCK_DATA_SOURCES } from "@/lib/mock/config";
import { fetchBff } from "@/services/bff-proxy";
import type { DataSourceRecord } from "@/types/config";

export async function GET() {
  const bff = await fetchBff<{ items: DataSourceRecord[]; path?: string }>(
    "/api/config/data-sources",
  );
  if (bff) return NextResponse.json(bff);
  return NextResponse.json({ items: MOCK_DATA_SOURCES, total: MOCK_DATA_SOURCES.length });
}

export async function PUT(req: NextRequest) {
  const body = await req.json();
  const bff = await fetchBff<{ items: DataSourceRecord[] }>(
    "/api/config/data-sources",
    { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(
    { error: "BFF unavailable — 请启动 V3 run-bff 以保存到 config/data_sources.json" },
    { status: 503 },
  );
}
