import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface PlacedCourse { offering_id: string; priority: number; }

/** place() 的結果。呼叫端（如 lib/analytics/track-plan）靠這個判斷是否真的新增、
 * 以及是不是本學期第一門課——store 自己**不得**有 analytics 副作用。 */
export interface PlaceOutcome { added: boolean; previousCount: number; placedCount: number; }

interface DraftState {
  schema_version: number;
  termKey: string;
  favorites: string[];
  placed: PlacedCourse[];
  setTerm: (termKey: string) => void;
  place: (offeringId: string) => PlaceOutcome;
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

      place: (offeringId) => {
        const before = get().placed;
        if (before.some((p) => p.offering_id === offeringId)) {
          return { added: false, previousCount: before.length, placedCount: before.length }; // dedup
        }
        const maxPrio = before.reduce((m, p) => Math.max(m, p.priority), 0);
        set({ placed: [...before, { offering_id: offeringId, priority: maxPrio + 1 }] });
        return { added: true, previousCount: before.length, placedCount: before.length + 1 };
      },

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
      name: "ntutbox-draft-_init",
      // one persisted blob per term: partition by termKey in the storage key.
      partialize: (s) => ({ schema_version: s.schema_version, termKey: s.termKey, favorites: s.favorites, placed: s.placed }),
      version: DRAFT_SCHEMA,
      migrate: (persisted, version) => {
        if (version !== DRAFT_SCHEMA) {
          // Unknown schema — return a safe empty draft rather than loading corrupt state.
          return { schema_version: DRAFT_SCHEMA, termKey: "", favorites: [], placed: [] };
        }
        return persisted as DraftState;
      },
    },
  ),
);
