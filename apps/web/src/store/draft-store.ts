import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface PlacedCourse { offering_id: string; priority: number; }

interface DraftState {
  schema_version: number;
  termKey: string;
  favorites: string[];
  placed: PlacedCourse[];
  setTerm: (termKey: string) => void;
  place: (offeringId: string) => void;
  unplace: (offeringId: string) => void;
  setPriority: (offeringId: string, priority: number) => void;
  toggleFavorite: (offeringId: string) => void;
  /** Drop placed/favorites not in validIds; returns dropped ids (spec §4 stale recovery). */
  reconcile: (validIds: Set<string>) => string[];
}

const DRAFT_SCHEMA = 1;

export const useDraftStore = create<DraftState>()(
  persist(
    (set, get) => ({
      schema_version: DRAFT_SCHEMA,
      termKey: "",
      favorites: [],
      placed: [],

      setTerm: (termKey) => set({ termKey }),

      place: (offeringId) => set((s) => {
        if (s.placed.some((p) => p.offering_id === offeringId)) return s; // dedup
        const maxPrio = s.placed.reduce((m, p) => Math.max(m, p.priority), 0);
        return { placed: [...s.placed, { offering_id: offeringId, priority: maxPrio + 1 }] };
      }),

      unplace: (offeringId) => set((s) => ({
        placed: s.placed.filter((p) => p.offering_id !== offeringId), // gaps allowed (spec §4)
      })),

      setPriority: (offeringId, priority) => set((s) => ({
        placed: s.placed.map((p) => (p.offering_id === offeringId ? { ...p, priority } : p)),
      })),

      toggleFavorite: (offeringId) => set((s) => ({
        favorites: s.favorites.includes(offeringId)
          ? s.favorites.filter((x) => x !== offeringId)
          : [...s.favorites, offeringId],
      })),

      reconcile: (validIds) => {
        const s = get();
        const dropped = [
          ...s.placed.map((p) => p.offering_id).filter((id) => !validIds.has(id)),
          ...s.favorites.filter((id) => !validIds.has(id)),
        ];
        if (dropped.length) {
          set({
            placed: s.placed.filter((p) => validIds.has(p.offering_id)),
            favorites: s.favorites.filter((id) => validIds.has(id)),
          });
        }
        return dropped;
      },
    }),
    {
      name: "ntutbox-draft",
      // one persisted blob per term: partition by termKey in the storage key.
      partialize: (s) => ({ schema_version: s.schema_version, termKey: s.termKey, favorites: s.favorites, placed: s.placed }),
    },
  ),
);
