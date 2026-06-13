"use client";
import { useMemo, useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
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
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
          active > 0
            ? "border-[var(--accent)]/40 bg-[var(--accent)]/12 text-[var(--accent)]"
            : "border-black/8 bg-white/55 text-[var(--ink-soft)] hover:bg-white/80",
        )}
      >
        {label}
        {active > 0 && (
          <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--accent)] px-1 text-[10px] font-bold text-white">
            {active}
          </span>
        )}
        <span className="text-[9px] opacity-60">▾</span>
      </PopoverTrigger>
      <PopoverContent align="start" className="glass-surface w-64 gap-2 p-2" sideOffset={6}>
        <div className="flex items-center gap-2">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={searchPlaceholder ?? `搜尋${label}…`}
            aria-label={`搜尋${label}`}
            className="min-w-0 flex-1 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs outline-none ring-1 ring-black/5 placeholder:text-zinc-400 focus:ring-[var(--accent)]/40"
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
            <p className="px-2 py-3 text-center text-xs text-zinc-400">無符合項目</p>
          )}
          {filtered.map((o) => {
            const on = selected.includes(o.value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => onToggle(o.value)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs transition-colors",
                  on ? "bg-[var(--accent)]/12 text-[var(--accent)]" : "hover:bg-black/5",
                )}
              >
                <span
                  className={cn(
                    "flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border text-[10px]",
                    on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-black/20",
                  )}
                >
                  {on ? "✓" : ""}
                </span>
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {o.hint && <span className="shrink-0 text-[10px] text-zinc-400">{o.hint}</span>}
              </button>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
