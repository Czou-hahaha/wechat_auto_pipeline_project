import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function GET() {
  const bff = await fetchBff<Record<string, unknown>>("/api/feedback/policy");
  if (!bff) {
    return NextResponse.json({ recommendation: {}, overrides: {} }, { status: 503 });
  }
  return NextResponse.json(bff);
}
