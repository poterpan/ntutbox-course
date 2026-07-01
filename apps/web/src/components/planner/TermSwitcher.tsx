"use client";
import { useEffect, useState } from "react";
import { getDataSource } from "@/lib/data";
import { useTermStore } from "@/store/term-store";
import { useTermBootstrap } from "@/lib/planner/use-term-bootstrap";
import { useUiStore } from "@/store/ui-store";

export function TermSwitcher() {
  const termKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const setSelectedTerm = useUiStore((s) => s.setSelectedTerm);
  const [terms, setTerms] = useState<string[]>([]);
  useTermBootstrap(selectedTerm);

  useEffect(() => {
    void getDataSource()
      .getManifest()
      .then((m) => setTerms(Object.keys(m.terms ?? {}).sort().reverse()));
  }, []);

  return (
    <select
      className="rounded-md border bg-white/70 px-2 py-1 text-sm"
      value={termKey ?? selectedTerm}
      onChange={(e) => setSelectedTerm(e.target.value)}
      aria-label="選擇學期"
    >
      {(terms.length ? terms : ["115-1"]).map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
    </select>
  );
}
