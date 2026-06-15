import { create } from "zustand";
import { EMPTY_FILTER, type FilterState } from "@/lib/filters/types";

export interface ActiveSlot { day: number; period: string; }

interface UiState {
  query: string;
  filters: FilterState;
  activeSlot: ActiveSlot | null;
  detailOfferingId: string | null;
  hoveredOfferingId: string | null; // desktop course-library hover → weekly-grid ghost preview
  viewMode: "week" | "day";
  selectedDay: number;       // for mobile day view
  libraryOpen: boolean;      // mobile bottom sheet
  libraryTab: "courses" | "favorites"; // right-panel content toggle
  staleDropped: string[];    // offering_ids removed by reconcile (spec §4 — never silently discard)
  setQuery: (q: string) => void;
  setFilters: (f: FilterState) => void;
  toggleFilterValue: (key: "weekdays" | "periods" | "colleges" | "units" | "classes" | "categories", value: string | number) => void;
  setEmiOnly: (v: boolean) => void;
  openSlot: (s: ActiveSlot | null) => void;
  openDetail: (id: string | null) => void;
  setHoveredOffering: (id: string | null) => void;
  setViewMode: (m: "week" | "day") => void;
  setSelectedDay: (d: number) => void;
  setLibraryOpen: (v: boolean) => void;
  setLibraryTab: (t: "courses" | "favorites") => void;
  setStaleDropped: (ids: string[]) => void;
  dismissStale: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  query: "", filters: EMPTY_FILTER, activeSlot: null, detailOfferingId: null, hoveredOfferingId: null,
  viewMode: "week", selectedDay: 1, libraryOpen: false, libraryTab: "courses", staleDropped: [],
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
  setHoveredOffering: (hoveredOfferingId) => set({ hoveredOfferingId }),
  setViewMode: (viewMode) => set({ viewMode }),
  setSelectedDay: (selectedDay) => set({ selectedDay }),
  setLibraryOpen: (libraryOpen) => set({ libraryOpen }),
  setLibraryTab: (libraryTab) => set({ libraryTab }),
  setStaleDropped: (staleDropped) => set({ staleDropped }),
  dismissStale: () => set({ staleDropped: [] }),
}));
