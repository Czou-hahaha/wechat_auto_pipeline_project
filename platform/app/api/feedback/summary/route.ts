import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function GET() {
  const bff = await fetchBff<Record<string, unknown>>("/api/feedback/summary");
  if (!bff) {
    return NextResponse.json(
      { total: 0, byStage: {}, byCategory: {}, latest: [] },
      { status: 503 },
    );
  }
  return NextResponse.json(bff);
}
