import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { EventMemorySnapshot } from "@/types/event";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const bff = await fetchBff<EventMemorySnapshot>(`/api/events/${id}/memory`);
  if (!bff) {
    return NextResponse.json({ error: "not_found_or_unavailable" }, { status: 404 });
  }
  return NextResponse.json(bff);
}

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const bff = await fetchBff<{ ok: boolean; snapshot: EventMemorySnapshot }>(
    `/api/events/${id}/memory/refresh`,
    { method: "POST" },
  );
  if (!bff) {
    return NextResponse.json({ error: "BFF unavailable" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
