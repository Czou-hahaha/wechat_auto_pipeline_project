import { NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";
import { fetchBff } from "@/services/bff-proxy";
import type { EventIntelligence } from "@/types/event";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const bff = await fetchBff<EventIntelligence>(`/api/events/${id}`);
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(
    {
      error: "bff_unreachable",
      message: `V6 BFF (${BFF_BASE}) 不可达，请运行 cd platform-v6 && npm run dev`,
    },
    { status: 503 },
  );
}
