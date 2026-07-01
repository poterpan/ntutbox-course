import { create } from "zustand";
import { EMPTY_FILTER, type FilterState, type EmiFilter } from "@/lib/filters/types";

// 英文授課三態循環：關閉 → 只看英文授課 → 排除英文授課 → 關閉。
const EMI_CYCLE: Record<EmiFilter, EmiFilter> = { all: "emi", emi: "non_emi", non_emi: "all" };

export interface ActiveSlot { day: number; period: string; }

interface UiState {
  query: string;
  selectedTerm: string;      // 檢視中的學期（提升自 TermSwitcher，供分享連結程式化切換）
  filters: FilterState;
  activeSlot: ActiveSlot | null;
  detailOfferingId: string | null;
  hoveredOfferingId: string | null; // desktop course-library hover → weekly-grid ghost preview
  viewMode: "week" | "day";
  selectedDay: number;       // for mobile day view
  libraryOpen: boolean;      // mobile bottom sheet
  libraryTab: "courses" | "favorites"; // right-panel content toggle
  staleDropped: string[];    // offering_ids removed by reconcile (spec §4 — never silently discard)
  sharedPlan: { termKey: string; offeringIds: string[] } | null; // 收到的分享課表（唯讀對比，非草稿）— F-B
  sharedPlanOpen: boolean;
  setQuery: (q: string) => void;
  setSelectedTerm: (t: string) => void;
  setFilters: (f: FilterState) => void;
  toggleFilterValue: (key: "weekdays" | "periods" | "colleges" | "units" | "classes" | "categories", value: string | number) => void;
  setEmi: (v: EmiFilter) => void;
  cycleEmi: () => void;
  openSlot: (s: ActiveSlot | null) => void;
  openDetail: (id: string | null) => void;
  setHoveredOffering: (id: string | null) => void;
  setViewMode: (m: "week" | "day") => void;
  setSelectedDay: (d: number) => void;
  setLibraryOpen: (v: boolean) => void;
  setLibraryTab: (t: "courses" | "favorites") => void;
  setStaleDropped: (ids: string[]) => void;
  dismissStale: () => void;
  openSharedPlan: (plan: { termKey: string; offeringIds: string[] }) => void;
  setSharedPlanOpen: (v: boolean) => void;
  clearSharedPlan: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  query: "", selectedTerm: "115-1", filters: EMPTY_FILTER, activeSlot: null, detailOfferingId: null, hoveredOfferingId: null,
  viewMode: "week", selectedDay: 1, libraryOpen: false, libraryTab: "courses", staleDropped: [],
  sharedPlan: null, sharedPlanOpen: false,
  setQuery: (query) => set({ query }),
  setSelectedTerm: (selectedTerm) => set({ selectedTerm }),
  setFilters: (filters) => set({ filters }),
  toggleFilterValue: (key, value) => set((s) => {
    const arr = s.filters[key] as (string | number)[];
    const next = arr.includes(value) ? arr.filter((x) => x !== value) : [...arr, value];
    return { filters: { ...s.filters, [key]: next } };
  }),
  setEmi: (emi) => set((s) => ({ filters: { ...s.filters, emi } })),
  cycleEmi: () => set((s) => ({ filters: { ...s.filters, emi: EMI_CYCLE[s.filters.emi] } })),
  openSlot: (activeSlot) => set({ activeSlot }),
  openDetail: (detailOfferingId) => set({ detailOfferingId }),
  setHoveredOffering: (hoveredOfferingId) => set({ hoveredOfferingId }),
  setViewMode: (viewMode) => set({ viewMode }),
  setSelectedDay: (selectedDay) => set({ selectedDay }),
  setLibraryOpen: (libraryOpen) => set({ libraryOpen }),
  setLibraryTab: (libraryTab) => set({ libraryTab }),
  setStaleDropped: (staleDropped) => set({ staleDropped }),
  dismissStale: () => set({ staleDropped: [] }),
  openSharedPlan: (sharedPlan) => set({ sharedPlan, sharedPlanOpen: true }),
  setSharedPlanOpen: (sharedPlanOpen) => set({ sharedPlanOpen }),
  clearSharedPlan: () => set({ sharedPlan: null, sharedPlanOpen: false }),
}));
