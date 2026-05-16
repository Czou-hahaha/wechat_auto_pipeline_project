import { NextRequest, NextResponse } from "next/server";
import { mockSearch } from "@/lib/mock/events";
import { fetchBff } from "@/services/bff-proxy";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q = sp.get("q") || "";
  const type = sp.get("type") || "event";
  const bff = await fetchBff<{ items: unknown[]; total: number; mode: string }>(
    `/api/search?${sp.toString()}`,
  );
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(mockSearch(q, type));
}
