import { NextRequest, NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { PromptContractPayload } from "@/types/config";

export async function GET() {
  const bff = await fetchBff<PromptContractPayload>("/api/prompts/contract");
  if (!bff) {
    return NextResponse.json(
      {
        contract: {
          objective: "BFF unavailable",
          hard_rules: [],
          effective_runtime: {},
          policy_overrides: {},
        },
      },
      { status: 503 },
    );
  }
  return NextResponse.json(bff);
}

export async function PUT(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const bff = await fetchBff<PromptContractPayload>("/api/prompts/contract", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!bff) {
    return NextResponse.json({ error: "BFF unavailable" }, { status: 503 });
  }
  return NextResponse.json(bff);
}
