import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function POST() {
  const bff = await fetchBff<{ total: number; items: Record<string, unknown>[] }>(
    "/api/sources/discover",
    { method: "POST" },
  );
  if (!bff) {
    return NextResponse.json({ error: "BFF unavailable" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
