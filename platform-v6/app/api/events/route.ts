import { NextRequest, NextResponse } from "next/server";
import { normalizeEventListItems } from "@/lib/event-summary-gate";
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
    return NextResponse.json({
      items,
      total: items.length,
      bffConnected: true,
    });
  }
  return NextResponse.json(
    {
      items: [],
      total: 0,
      bffConnected: false,
      error: "V6 BFF (:8788) 不可达，请启动 run-bff",
    },
    { status: 503 },
  );
}
