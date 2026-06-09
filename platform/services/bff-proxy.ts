import { BFF_BASE } from "@/lib/constants";

export async function fetchBff<T>(
  path: string,
  init?: RequestInit & { method?: string; body?: string },
): Promise<T | null> {
  const url = `${BFF_BASE}${path.startsWith("/") ? path : `/${path}`}`;
  try {
    const res = await fetch(url, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
      next: { revalidate: 0 },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
