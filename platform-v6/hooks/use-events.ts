"use client";

import { useQuery } from "@tanstack/react-query";
import type {
  DashboardData,
  EventIntelligence,
  EventListItem,
  QAReviewItem,
} from "@/types/event";
import type { EventSort } from "@/store/event-filters";

type EventsListResponse = {
  items: EventListItem[];
  total: number;
  bffConnected?: boolean;
  error?: string;
};

async function jsonFetch<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json() as Promise<T>;
}

async function fetchEventsList(url: string): Promise<EventsListResponse> {
  const res = await fetch(url);
  const body = (await res.json()) as EventsListResponse;
  if (!res.ok) {
    return {
      items: [],
      total: 0,
      bffConnected: false,
      error: body.error || `HTTP ${res.status}`,
    };
  }
  return body;
}

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => jsonFetch<DashboardData>("/api/dashboard"),
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: 30_000,
  });
}

export function useEvents(params: {
  q?: string;
  keyword?: string;
  minImportance?: number;
  sort?: EventSort;
}) {
  const sp = new URLSearchParams();
  if (params.q) sp.set("q", params.q);
  if (params.keyword) sp.set("keyword", params.keyword);
  if (params.minImportance) sp.set("min_importance", String(params.minImportance));
  if (params.sort) sp.set("sort", params.sort);
  return useQuery({
    queryKey: ["events", params],
    queryFn: () => fetchEventsList(`/api/events?${sp}`),
    staleTime: 60_000,
    placeholderData: (prev) => prev,
  });
}

export function useEvent(id: string) {
  return useQuery({
    queryKey: ["event", id],
    queryFn: () => jsonFetch<EventIntelligence>(`/api/events/${id}`),
    enabled: Boolean(id),
  });
}

export function useQAReviews(minScore = 0, maxScore = 100) {
  return useQuery({
    queryKey: ["qa", minScore, maxScore],
    queryFn: () =>
      jsonFetch<{ items: QAReviewItem[]; total: number }>(
        `/api/qa?min_score=${minScore}&max_score=${maxScore}`,
      ),
  });
}

export function useSearchQuery(q: string) {
  return useQuery({
    queryKey: ["search", q],
    queryFn: () =>
      jsonFetch<{ items: EventListItem[]; total: number; mode: string }>(
        `/api/search?q=${encodeURIComponent(q)}`,
      ),
    enabled: q.length > 0,
  });
}
