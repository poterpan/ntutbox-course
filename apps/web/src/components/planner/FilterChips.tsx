"use client";
import { useUiStore } from "@/store/ui-store";
import { allColleges } from "@/lib/filters/college-map";
import { cn } from "@/lib/utils";

const WEEKDAYS: [number, string][] = [[1, "一"], [2, "二"], [3, "三"], [4, "四"], [5, "五"], [6, "六"]];
const PERIODS = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"];

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={cn("rounded-full border px-3 py-1 text-xs transition-colors",
        active ? "border-sky-300 bg-sky-100 text-sky-800" : "border-zinc-200 bg-white/60 text-zinc-600 hover:bg-white")}>
      {children}
    </button>
  );
}

export function FilterChips({ units, classes }: { units: { code: string; name: string }[]; classes: { code: string; name: string; kind?: string }[] }) {
  const { filters, toggleFilterValue, setEmiOnly } = useUiStore();
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1">
        {WEEKDAYS.map(([d, l]) => <Chip key={d} active={filters.weekdays.includes(d)} onClick={() => toggleFilterValue("weekdays", d)}>{l}</Chip>)}
      </div>
      <div className="flex flex-wrap gap-1">
        {PERIODS.map((p) => <Chip key={p} active={filters.periods.includes(p)} onClick={() => toggleFilterValue("periods", p)}>{p}</Chip>)}
      </div>
      <div className="flex flex-wrap gap-1">
        {allColleges().map((c) => <Chip key={c} active={filters.colleges.includes(c)} onClick={() => toggleFilterValue("colleges", c)}>{c}</Chip>)}
      </div>
      <div className="flex flex-wrap gap-1">
        {units.map((u) => <Chip key={u.code} active={filters.units.includes(u.code)} onClick={() => toggleFilterValue("units", u.code)}>{u.name || u.code}</Chip>)}
      </div>
      <div className="flex flex-wrap gap-1">
        {classes.map((k) => (
          <Chip key={k.code} active={filters.classes.includes(k.code)} onClick={() => toggleFilterValue("classes", k.code)}>
            {k.name}{k.kind && k.kind !== "regular" ? `（${k.kind === "pool" ? "池" : "佔位"}）` : ""}
          </Chip>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        <Chip active={filters.emiOnly} onClick={() => setEmiOnly(!filters.emiOnly)}>英文授課</Chip>
      </div>
    </div>
  );
}
