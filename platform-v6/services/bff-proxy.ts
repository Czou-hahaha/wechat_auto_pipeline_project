import { BFF_BASE } from "@/lib/constants";

const DEFAULT_TIMEOUT_MS = 30_000;
const EVENTS_TIMEOUT_MS = 90_000;

function timeoutFor(path: string): number {
  if (path.startsWith("/api/events") || path === "/health") {
    return EVENTS_TIMEOUT_MS;
  }
  return DEFAULT_TIMEOUT_MS;
}

export async function fetchBff<T>(
  path: string,
  init?: RequestInit & { method?: string; body?: string },
): Promise<T | null> {
  const url = `${BFF_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  const timeoutMs = timeoutFor(path.startsWith("/") ? path : `/${path}`);
  try {
    const res = await fetch(url, {
      ...init,
      cache: "no-store",
      headers: { Accept: "application/json", ...init?.headers },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) {
      if (process.env.NODE_ENV === "development") {
        console.error(`[bff-proxy] ${init?.method || "GET"} ${url} → HTTP ${res.status}`);
      }
      return null;
    }
    return (await res.json()) as T;
  } catch (err) {
    if (process.env.NODE_ENV === "development") {
      console.error(`[bff-proxy] ${init?.method || "GET"} ${url} failed:`, err);
    }
    return null;
  }
}

export function bffConnectedResponse() {
  return { connected: false as const, bffUrl: BFF_BASE };
}
