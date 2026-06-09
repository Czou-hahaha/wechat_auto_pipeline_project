import { NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";
import { fetchBff } from "@/services/bff-proxy";

export async function GET() {
  const bff = await fetchBff<{ status: string; service?: string }>("/health");
  if (bff?.status === "ok") {
    return NextResponse.json({
      connected: true,
      service: bff.service || "v3-bff",
      bffUrl: BFF_BASE,
    });
  }
  return NextResponse.json({
    connected: false,
    bffUrl: BFF_BASE,
    hint: "请运行 cd platform-v6 && npm run dev（会自动启动 V6 BFF :8788）",
  });
}
