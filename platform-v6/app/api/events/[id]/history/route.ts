import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { EventHistoryPayload } from "@/types/event";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const bff = await fetchBff<EventHistoryPayload>(`/api/events/${id}/history`);
  if (!bff) {
    return NextResponse.json({ error: "BFF unavailable" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
