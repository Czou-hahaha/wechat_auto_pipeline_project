import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";

export async function POST(
  _req: Request,
  { params }: { params: Promise<{ host: string }> },
) {
  const { host } = await params;
  const bff = await fetchBff<{ ok: boolean; item: Record<string, unknown> }>(
    `/api/sources/candidates/${encodeURIComponent(host)}/probe`,
    { method: "POST" },
  );
  if (!bff) {
    return NextResponse.json({ error: "BFF unavailable" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
