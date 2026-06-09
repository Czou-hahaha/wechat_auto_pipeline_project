import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function GET() {
  const bff = await fetchBff<{ total_sec?: number; phases?: Record<string, number> }>(
    "/api/pipeline/phase-timings",
  );
  if (!bff) {
    return NextResponse.json({ total_sec: 0, phases: {} }, { status: 503 });
  }
  return NextResponse.json(bff);
}
