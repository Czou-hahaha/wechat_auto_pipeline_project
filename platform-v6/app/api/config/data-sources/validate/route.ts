import { NextRequest, NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const url = `${BFF_BASE}/api/config/data-sources/validate`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { ok: false, status: "failed", message: "BFF 不可用，无法验证数据源" },
      { status: 503 },
    );
  }
}
