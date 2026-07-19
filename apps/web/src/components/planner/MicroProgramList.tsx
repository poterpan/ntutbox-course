"use client";
import { useMemo, useState } from "react";
import { useMprograms } from "@/lib/planner/use-mprograms";
import { OAA_MPROGRAM_URL } from "@/lib/planner/mprogram-links";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { SearchInput } from "@/components/ui/search-input";
import { AccentButton } from "@/components/ui/accent-button";

// OAA 微學程專區外連（清單底部固定）——完整規定與 PDF 只在教務處官網，站內不重製。
function OaaLink() {
  return (
    <a
      href={OAA_MPROGRAM_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="text-[12px] text-[var(--ink-soft)] underline"
    >
      教務處微學程專區（完整規定與 PDF）↗
    </a>
  );
}

export function MicroProgramList() {
  // termKey：比照 TermSwitcher — term-store 優先、fallback ui-store（兩 hook 無條件呼叫再合併）。
  const storeTermKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const termKey = storeTermKey ?? selectedTerm;
  const setSelectedProgramCode = useUiStore((s) => s.setSelectedProgramCode);

  const { data, loading, error, retry } = useMprograms(termKey);
  const [query, setQuery] = useState("");

  const programs = useMemo(() => {
    const all = data?.programs ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (p) => p.name.toLowerCase().includes(q) || p.code.toLowerCase().includes(q),
    );
  }, [data, query]);

  return (
    <div className="flex h-full flex-col gap-3 p-4 pt-3">
      <SearchInput
        variant="inset"
        type="search"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="搜尋微學程…"
        aria-label="搜尋微學程"
      />

      <div className="min-h-0 flex-1 overflow-y-auto">
        {error ? (
          <div className="flex flex-col items-center gap-3 pt-8 text-center">
            <p className="text-sm text-[var(--ink-soft)]">載入微學程失敗</p>
            <AccentButton tone="soft" onClick={retry}>
              重試
            </AccentButton>
          </div>
        ) : loading ? (
          <ul className="flex flex-col gap-1.5" aria-hidden>
            {Array.from({ length: 6 }).map((_, i) => (
              <li key={i} className="h-11 animate-pulse rounded-xl bg-black/[0.05]" />
            ))}
          </ul>
        ) : programs.length === 0 ? (
          <p className="pt-8 text-center text-sm text-[var(--ink-soft)]">沒有符合的學程</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {programs.map((p) => (
              <li key={p.code}>
                <button
                  type="button"
                  onClick={() => setSelectedProgramCode(p.code)}
                  className="flex w-full items-center gap-2 rounded-xl bg-white px-3 py-2.5 text-left ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/[0.06] hover:ring-[var(--accent)]/30"
                >
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-[var(--ink)]">
                    {p.name}
                  </span>
                  <span className="shrink-0 text-[11px] tabular-nums text-[var(--ink-soft)]">
                    {p.offering_ids?.length ?? 0} 門開課
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="shrink-0 border-t border-black/[0.06] pt-3">
        <OaaLink />
      </div>
    </div>
  );
}
