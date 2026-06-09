import { NextRequest, NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";
import { normalizeEventListItems } from "@/lib/event-summary-gate";
import { fetchBff } from "@/services/bff-proxy";
import type { EventListItem } from "@/types/event";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const bff = await fetchBff<{
    items: EventListItem[];
    total: number;
    mode: string;
  }>(`/api/search?${sp.toString()}`);
  if (bff) {
    const items = normalizeEventListItems(bff.items ?? []);
    return NextResponse.json({ ...bff, items, total: items.length });
  }
  return NextResponse.json(
    {
      items: [],
      total: 0,
      mode: "unavailable",
      error: `V6 BFF (${BFF_BASE}) 不可达`,
    },
    { status: 503 },
  );
}
