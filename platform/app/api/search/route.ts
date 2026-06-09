import { NextRequest, NextResponse } from "next/server";
import { normalizeEventListItems } from "@/lib/event-summary-gate";
import { mockSearch } from "@/lib/mock/events";
import { fetchBff } from "@/services/bff-proxy";
import type { EventListItem } from "@/types/event";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const q = sp.get("q") || "";
  const type = sp.get("type") || "event";
  const bff = await fetchBff<{
    items: EventListItem[];
    total: number;
    mode: string;
  }>(`/api/search?${sp.toString()}`);
  if (bff) {
    const items = normalizeEventListItems(bff.items ?? []);
    return NextResponse.json({ ...bff, items, total: items.length });
  }
  return NextResponse.json(mockSearch(q, type));
}
