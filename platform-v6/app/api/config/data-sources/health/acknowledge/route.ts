import { NextRequest, NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const bff = await fetchBff("/api/config/data-sources/health/acknowledge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!bff) {
    return NextResponse.json({ error: "BFF 不可用" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
