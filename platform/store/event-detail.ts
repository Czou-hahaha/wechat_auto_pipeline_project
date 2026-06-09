import { create } from "zustand";

interface EventDetailState {
  selectedParagraphId: string | null;
  rightTab: "sources" | "qa" | "grounding";
  setSelectedParagraphId: (id: string | null) => void;
  setRightTab: (tab: "sources" | "qa" | "grounding") => void;
}

export const useEventDetailStore = create<EventDetailState>((set) => ({
  selectedParagraphId: null,
  rightTab: "grounding",
  setSelectedParagraphId: (selectedParagraphId) =>
    set({ selectedParagraphId, rightTab: "grounding" }),
  setRightTab: (rightTab) => set({ rightTab }),
}));
