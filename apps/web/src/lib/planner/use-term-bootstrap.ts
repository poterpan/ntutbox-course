"use client";
import { useEffect } from "react";
import { getDataSource } from "@/lib/data";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";
import { useUiStore } from "@/store/ui-store";

const DEFAULT_TERM = "115-1";

/** Loads a term, swaps the per-term persisted draft, and reconciles stale entries. */
export function useTermBootstrap(termKey: string = DEFAULT_TERM) {
  const loadTerm = useTermStore((s) => s.loadTerm);
  const bundle = useTermStore((s) => s.bundle);
  const status = useTermStore((s) => s.status);

  useEffect(() => {
    // per-term persistence key (spec §4 — draft isolated by term)
    useDraftStore.persist.setOptions({ name: `ntutbox-draft-${termKey}` });
    void useDraftStore.persist.rehydrate();
    useDraftStore.getState().setTerm(termKey);
    void loadTerm(termKey, getDataSource());
  }, [termKey, loadTerm]);

  useEffect(() => {
    if (status === "ready" && bundle) {
      const valid = new Set((bundle.catalog.courses ?? []).map((c) => c.offering_id));
      const dropped = useDraftStore.getState().reconcile(valid);
      if (dropped.length) {
        useUiStore.getState().setStaleDropped(dropped);
      }
    }
  }, [status, bundle]);
}
