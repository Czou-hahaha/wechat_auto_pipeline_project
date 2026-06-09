import { NextResponse } from "next/server";
import { fetchBff } from "@/services/bff-proxy";
import type { PromptPreviewPayload } from "@/types/config";

export async function GET() {
  const bff = await fetchBff<PromptPreviewPayload>("/api/prompts/preview");
  if (!bff) {
    return NextResponse.json(
      { version: "n/a", systemPreview: "", userTemplatePreview: "" },
      { status: 503 },
    );
  }
  return NextResponse.json(bff);
}
