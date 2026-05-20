import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function GET() {
  const bff = await fetchBff<{ status: string; service?: string }>("/health");
  if (bff?.status === "ok") {
    return NextResponse.json({
      connected: true,
      service: bff.service || "v3-bff",
    });
  }
  return NextResponse.json({ connected: false });
}
