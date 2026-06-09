import { NextResponse } from "next/server";
import { BFF_BASE } from "@/lib/constants";

export async function POST() {
  const url = `${BFF_BASE}/api/pipeline/run-once`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json" },
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      return NextResponse.json(
        {
          ok: false,
          error: (body as { detail?: string }).detail || "start_failed",
          message:
            res.status === 409
              ? "已有采集任务在运行，请等待完成后再试。"
              : "启动采集失败",
        },
        { status: res.status },
      );
    }
    return NextResponse.json(body);
  } catch {
    return NextResponse.json(
      {
        ok: false,
        error: "bff_unavailable",
        message:
          "无法连接 V6 BFF (:8788)。请运行：cd platform-v6 && npm run dev",
      },
      { status: 503 },
    );
  }
}
