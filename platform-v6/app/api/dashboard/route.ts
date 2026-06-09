import { NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";
import { fetchBff } from "@/services/bff-proxy";
import type { DashboardData } from "@/types/event";

export async function GET() {
  const bff = await fetchBff<DashboardData>("/api/dashboard");
  if (bff) {
    return NextResponse.json(bff, {
      headers: { "Cache-Control": "no-store, max-age=0" },
    });
  }
  return NextResponse.json(
    {
      error: "bff_unreachable",
      message: `V6 BFF (${BFF_BASE}) 不可达，请运行 cd platform-v6 && npm run dev`,
    },
    { status: 503 },
  );
}
