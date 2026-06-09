import { NextRequest, NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";
import { fetchBff } from "@/services/bff-proxy";

export async function GET(req: NextRequest) {
  const sp = req.nextUrl.searchParams;
  const qs = sp.toString();
  const bff = await fetchBff<{ items: unknown[]; total?: number }>(`/api/qa?${qs}`);
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(
    {
      items: [],
      total: 0,
      error: `V6 BFF (${BFF_BASE}) 不可达`,
    },
    { status: 503 },
  );
}
