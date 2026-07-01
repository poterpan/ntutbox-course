"use client";
import { useMemo, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { SearchInput } from "@/components/ui/search-input";
import { filterChipVariants, CountBadge } from "@/components/ui/filter-chip";
import { cn } from "@/lib/utils";

export interface ComboOption {
  value: string;
  label: string;
  hint?: string; // e.g. "（池）" / code
}

/**
 * Compact searchable multi-select dropdown. Replaces the 系所/班級/學院 chip walls.
 * Trigger shows the active count; popover has a search box + scrollable toggle list.
 */
export function FilterCombobox({
  label,
  options,
  selected,
  onToggle,
  onClear,
  searchPlaceholder,
}: {
  label: string;
  options: ComboOption[];
  selected: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
  searchPlaceholder?: string;
}) {
  const [q, setQ] = useState("");
  const active = selected.length;
  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n) return options;
    return options.filter(
      (o) => o.label.toLowerCase().includes(n) || o.value.toLowerCase().includes(n),
    );
  }, [q, options]);

  return (
    <Popover>
      <PopoverTrigger
        className={cn("inline-flex items-center gap-1.5", filterChipVariants({ active: active > 0 }))}
      >
        {label}
        {active > 0 && <CountBadge>{active}</CountBadge>}
        <span className="text-[9px] opacity-70">▾</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 gap-2 border-black/10 bg-white p-2 shadow-xl" sideOffset={6}>
        <div className="flex items-center gap-2">
          <SearchInput
            variant="popover"
            className="min-w-0 flex-1"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={searchPlaceholder ?? `搜尋${label}…`}
            aria-label={`搜尋${label}`}
          />
          {active > 0 && (
            <button
              type="button"
              onClick={onClear}
              className="shrink-0 rounded-md px-1.5 py-1 text-[11px] text-[var(--accent)] hover:bg-[var(--accent)]/10"
            >
              清除
            </button>
          )}
        </div>
        <div className="thin-scroll max-h-64 overflow-y-auto pr-0.5">
          {filtered.length === 0 && (
            <p className="px-2 py-3 text-center text-xs text-[var(--ink-soft)]">無符合項目</p>
          )}
          {filtered.map((o, i) => {
            const on = selected.includes(o.value);
            // Merge consecutive selected rows into one block: only the run's
            // outer corners are rounded (iOS grouped-list feel).
            const prevOn = i > 0 && selected.includes(filtered[i - 1].value);
            const nextOn = i < filtered.length - 1 && selected.includes(filtered[i + 1].value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => onToggle(o.value)}
                className={cn(
                  "flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs transition-colors",
                  on
                    ? cn(
                        "bg-[var(--accent)]/12 font-semibold text-[var(--accent-ink)]",
                        prevOn ? "rounded-t-none" : "rounded-t-lg",
                        nextOn ? "rounded-b-none" : "rounded-b-lg",
                      )
                    : "rounded-lg text-[var(--ink)] hover:bg-black/5",
                )}
              >
                <span
                  className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded-md border",
                    on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-black/25",
                  )}
                >
                  {on && (
                    <svg className="size-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={3} aria-hidden>
                      <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </span>
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {o.hint && <span className="shrink-0 text-[10px] text-[var(--ink-soft)]">{o.hint}</span>}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
