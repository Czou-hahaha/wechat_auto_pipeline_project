import { create } from "zustand";

export type SearchMode = "semantic" | "event" | "keyword";

interface SearchState {
  query: string;
  mode: SearchMode;
  setQuery: (q: string) => void;
  setMode: (m: SearchMode) => void;
}

export const useSearchStore = create<SearchState>((set) => ({
  query: "",
  mode: "event",
  setQuery: (query) => set({ query }),
  setMode: (mode) => set({ mode }),
}));
