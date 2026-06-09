import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { SourceCandidateRecord } from "@/types/config";

export async function GET() {
  const bff = await fetchBff<{ items: SourceCandidateRecord[]; total: number }>(
    "/api/sources/candidates",
  );
  if (!bff) {
    return NextResponse.json({ items: [], total: 0 }, { status: 503 });
  }
  return NextResponse.json(bff);
}
