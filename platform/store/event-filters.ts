import { create } from "zustand";

export type EventSort = "importance" | "recent" | "qa";

interface EventFiltersState {
  query: string;
  keyword: string;
  minImportance: number;
  sort: EventSort;
  setQuery: (q: string) => void;
  setKeyword: (k: string) => void;
  setMinImportance: (n: number) => void;
  setSort: (s: EventSort) => void;
  reset: () => void;
}

const initial = {
  query: "",
  keyword: "",
  minImportance: 0,
  sort: "recent" as EventSort,
};

export const useEventFiltersStore = create<EventFiltersState>((set) => ({
  ...initial,
  setQuery: (query) => set({ query }),
  setKeyword: (keyword) => set({ keyword }),
  setMinImportance: (minImportance) => set({ minImportance }),
  setSort: (sort) => set({ sort }),
  reset: () => set(initial),
}));
