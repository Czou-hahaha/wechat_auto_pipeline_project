import { NextResponse } from "next/server";
import { mockEventById } from "@/lib/mock/events";
import { fetchBff } from "@/services/bff-proxy";
import type { EventIntelligence } from "@/types/event";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const bff = await fetchBff<EventIntelligence>(`/api/events/${id}`);
  if (bff) return NextResponse.json(bff);
  const mock = mockEventById(id);
  if (!mock) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json(mock);
}
