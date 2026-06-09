import { NextRequest, NextResponse } from "next/server";
import { normalizeEventListItems } from "@/lib/event-summary-gate";
import { mockEventList } from "@/lib/mock/events";
import { fetchBff } from "@/services/bff-proxy";
import type { EventListItem } from "@/types/event";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const qs = new URLSearchParams(sp).toString();
  const bff = await fetchBff<{ items: EventListItem[]; total: number }>(
    `/api/events?${qs}`,
  );
  if (bff) {
    const items = normalizeEventListItems(bff.items ?? []);
    return NextResponse.json({ items, total: items.length });
  }
  let items = normalizeEventListItems(mockEventList());
  const q = sp.get("q") || sp.get("keyword") || "";
  const min = Number(sp.get("min_importance") || 0);
  if (q) {
    const needle = q.toLowerCase();
    items = items.filter(
      (e) =>
        e.title.toLowerCase().includes(needle) ||
        e.keywords.some((k) => k.toLowerCase().includes(needle)),
    );
  }
  if (min > 0) items = items.filter((e) => e.importance_score >= min);
  return NextResponse.json({ items, total: items.length });
}
