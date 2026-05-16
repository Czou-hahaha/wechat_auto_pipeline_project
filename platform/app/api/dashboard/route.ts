import { NextResponse } from "next/server";
import { mockDashboard } from "@/lib/mock/events";
import { fetchBff } from "@/services/bff-proxy";
import type { DashboardData } from "@/types/event";

export async function GET() {
  const bff = await fetchBff<DashboardData>("/api/dashboard");
  if (bff) return NextResponse.json(bff);
  return NextResponse.json(mockDashboard());
}
