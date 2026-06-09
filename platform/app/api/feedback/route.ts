import { NextRequest, NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const bff = await fetchBff<{ ok: boolean; item: Record<string, unknown> }>(
    "/api/feedback",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  if (!bff) {
    return NextResponse.json({ error: "BFF unavailable" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
