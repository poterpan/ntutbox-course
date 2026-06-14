import { create } from "zustand";
import type { DataSource } from "@/lib/data";
import type { TermBundle } from "@/lib/data/types";

type Status = "idle" | "loading" | "ready" | "error";

interface TermState {
  status: Status;
  termKey: string | null;
  bundle: TermBundle | null;
  error: string | null;
  generation: number;
  loadTerm: (termKey: string, ds: DataSource) => Promise<void>;
  catalogCrawledAt: () => string | null;
  enrollmentObservedAt: () => string | null;
}

export const useTermStore = create<TermState>((set, get) => ({
  status: "idle",
  termKey: null,
  bundle: null,
  error: null,
  generation: 0,

  async loadTerm(termKey, ds) {
    const gen = get().generation + 1;
    set({ generation: gen, status: "loading", error: null });
    try {
      const bundle = await ds.getTerm(termKey);
      if (get().generation !== gen) return; // superseded — discard stale result
      set({ status: "ready", termKey, bundle });
    } catch (e) {
      if (get().generation !== gen) return;
      set({ status: "error", error: e instanceof Error ? e.message : String(e) });
    }
  },

  catalogCrawledAt: () => get().bundle?.catalog.freshness?.catalog_crawled_at ?? null,
  enrollmentObservedAt: () => get().bundle?.enrollment?.observed_at ?? null,
}));
