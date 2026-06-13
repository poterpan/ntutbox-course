import { create } from "zustand";
import { EMPTY_FILTER, type FilterState } from "@/lib/filters/types";

export interface ActiveSlot { day: number; period: string; }

interface UiState {
  query: string;
  filters: FilterState;
  activeSlot: ActiveSlot | null;
  detailOfferingId: string | null;
  viewMode: "week" | "day";
  selectedDay: number;       // for mobile day view
  libraryOpen: boolean;      // mobile bottom sheet
  setQuery: (q: string) => void;
  setFilters: (f: FilterState) => void;
  toggleFilterValue: (key: "weekdays" | "periods" | "colleges" | "units" | "classes", value: string | number) => void;
  setEmiOnly: (v: boolean) => void;
  openSlot: (s: ActiveSlot | null) => void;
  openDetail: (id: string | null) => void;
  setViewMode: (m: "week" | "day") => void;
  setSelectedDay: (d: number) => void;
  setLibraryOpen: (v: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  query: "", filters: EMPTY_FILTER, activeSlot: null, detailOfferingId: null,
  viewMode: "week", selectedDay: 1, libraryOpen: false,
  setQuery: (query) => set({ query }),
  setFilters: (filters) => set({ filters }),
  toggleFilterValue: (key, value) => set((s) => {
    const arr = s.filters[key] as (string | number)[];
    const next = arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value];
    return { filters: { ...s.filters, [key]: next } };
  }),
  setEmiOnly: (emiOnly) => set((s) => ({ filters: { ...s.filters, emiOnly } })),
  openSlot: (activeSlot) => set({ activeSlot }),
  openDetail: (detailOfferingId) => set({ detailOfferingId }),
  setViewMode: (viewMode) => set({ viewMode }),
  setSelectedDay: (selectedDay) => set({ selectedDay }),
  setLibraryOpen: (libraryOpen) => set({ libraryOpen }),
}));
