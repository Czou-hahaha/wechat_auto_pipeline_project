import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function GET() {
  const bff = await fetchBff("/api/config/data-sources/health");
  if (!bff) {
    return NextResponse.json(
      { sources: {}, alerts: [], summary: { total: 0, ok: 0, failed: 0, needs_attention: 0 } },
      { status: 503 },
    );
  }
  return NextResponse.json(bff);
}

export async function POST() {
  const bff = await fetchBff("/api/config/data-sources/health/scan", { method: "POST" });
  if (!bff) {
    return NextResponse.json({ error: "BFF 不可用" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
