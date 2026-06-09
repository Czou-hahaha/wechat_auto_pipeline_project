import { NextRequest, NextResponse } from "next/server";
import { MOCK_KEYWORDS } from "@/lib/mock/config";
import { fetchBff } from "@/services/bff-proxy";
import type { KeywordsConfig } from "@/types/config";

export async function GET() {
  const bff = await fetchBff<{ data: KeywordsConfig; path?: string }>(
    "/api/config/keywords",
  );
  if (bff) return NextResponse.json(bff);
  return NextResponse.json({ data: MOCK_KEYWORDS });
}

export async function PUT(req: NextRequest) {
  const body = await req.json();
  const bff = await fetchBff<{ data: KeywordsConfig }>("/api/config/keywords", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(
    { error: "BFF unavailable — 请启动 V3 run-bff 以保存到 config/search_keywords.json" },
    { status: 503 },
  );
}
