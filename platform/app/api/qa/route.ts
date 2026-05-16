import { NextRequest, NextResponse } from "next/server";
import { mockQAReviews } from "@/lib/mock/events";
import { fetchBff } from "@/services/bff-proxy";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const qs = sp.toString();
  const bff = await fetchBff<{ items: unknown[] }>(`/api/qa?${qs}`);
  if (bff) return NextResponse.json(bff);
  let items = mockQAReviews();
  const min = Number(sp.get("min_score") || 0);
  const max = Number(sp.get("max_score") || 100);
  items = items.filter((i) => i.qa.score >= min && i.qa.score <= max);
  return NextResponse.json({ items, total: items.length });
}
