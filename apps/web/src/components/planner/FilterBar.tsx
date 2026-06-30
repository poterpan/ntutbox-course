"use client";
import { useUiStore } from "@/store/ui-store";
import { EMPTY_FILTER } from "@/lib/filters/types";
import { allColleges } from "@/lib/filters/college-map";
import { FilterCombobox, type ComboOption } from "./FilterCombobox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { filterChipVariants, CountBadge } from "@/components/ui/filter-chip";
import { cn } from "@/lib/utils";

const WEEKDAYS: [number, string][] = [[1, "一"], [2, "二"], [3, "三"], [4, "四"], [5, "五"], [6, "六"]];
const PERIODS = ["1", "2", "3", "4", "N", "5", "6", "7", "8", "9", "A", "B", "C", "D"];

export interface UnitOption { code: string; name: string }
export interface ClassOption { code: string; name: string; kind?: string }

export function FilterBar({ units, classes }: { units: UnitOption[]; classes: ClassOption[] }) {
  const { filters, toggleFilterValue, cycleEmi, setFilters } = useUiStore();

  const collegeOpts: ComboOption[] = allColleges().map((c) => ({ value: c, label: c }));
  const unitOpts: ComboOption[] = units.map((u) => ({ value: u.code, label: u.name || u.code }));
  const classOpts: ComboOption[] = classes.map((k) => ({
    value: k.code,
    label: k.name,
    hint: k.kind === "pool" ? "池" : k.kind === "virtual" ? "佔位" : undefined,
  }));

  const timeActive = filters.weekdays.length + filters.periods.length;
  const anyActive =
    filters.weekdays.length || filters.periods.length || filters.colleges.length ||
    filters.units.length || filters.classes.length || filters.categories.length || filters.emi !== "all";

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <FilterCombobox
        label="學院" options={collegeOpts} selected={filters.colleges}
        onToggle={(v) => toggleFilterValue("colleges", v)}
        onClear={() => setFilters({ ...filters, colleges: [] })}
      />
      <FilterCombobox
        label="系所" options={unitOpts} selected={filters.units}
        onToggle={(v) => toggleFilterValue("units", v)}
        onClear={() => setFilters({ ...filters, units: [] })}
      />
      <FilterCombobox
        label="班級" options={classOpts} selected={filters.classes}
        onToggle={(v) => toggleFilterValue("classes", v)}
        onClear={() => setFilters({ ...filters, classes: [] })}
      />

      {/* 時間 (weekday + period) */}
      <Popover>
        <PopoverTrigger
          className={cn("inline-flex items-center gap-1.5", filterChipVariants({ active: timeActive > 0 }))}
        >
          時間
          {timeActive > 0 && <CountBadge>{timeActive}</CountBadge>}
          <span className="text-[9px] opacity-70">▾</span>
        </PopoverTrigger>
        <PopoverContent align="start" sideOffset={6} className="w-64 gap-3 border-black/10 bg-white p-3 shadow-xl">
          <div>
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">星期</div>
            <div className="flex flex-wrap gap-1">
              {WEEKDAYS.map(([d, l]) => (
                <Toggle key={d} on={filters.weekdays.includes(d)} onClick={() => toggleFilterValue("weekdays", d)}>{l}</Toggle>
              ))}
            </div>
          </div>
          <div>
            <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--ink-soft)]">節次</div>
            <div className="flex flex-wrap gap-1">
              {PERIODS.map((p) => (
                <Toggle key={p} on={filters.periods.includes(p)} onClick={() => toggleFilterValue("periods", p)}>{p}</Toggle>
              ))}
            </div>
          </div>
        </PopoverContent>
      </Popover>

      {([["required", "必修"], ["elective", "選修"]] as const).map(([val, label]) => {
        const on = filters.categories.includes(val);
        return (
          <button
            key={val}
            type="button"
            aria-pressed={on}
            onClick={() => toggleFilterValue("categories", val)}
            className={filterChipVariants({ active: on })}
          >
            {on ? "✓ " : ""}{label}
          </button>
        );
      })}

      <button
        type="button"
        aria-label={`英文授課篩選：${filters.emi === "all" ? "關閉" : filters.emi === "emi" ? "只看英文授課" : "排除英文授課"}（點擊循環）`}
        onClick={cycleEmi}
        className={filterChipVariants({ active: filters.emi !== "all" })}
      >
        {filters.emi === "emi" ? "✓ 英文授課" : filters.emi === "non_emi" ? "✕ 非英文授課" : "英文授課"}
      </button>

      {anyActive ? (
        <button
          type="button"
          onClick={() => setFilters(EMPTY_FILTER)}
          className="ml-auto rounded-full px-2.5 py-1.5 text-[11px] text-[var(--ink-soft)] hover:text-[var(--accent)]"
        >
          清除全部
        </button>
      ) : null}
    </div>
  );
}

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex h-7 min-w-7 items-center justify-center rounded-lg border px-2 text-xs transition-colors",
        on ? "border-[var(--accent)] bg-[var(--accent)] text-white" : "border-black/10 bg-white/60 text-[var(--ink-soft)] hover:bg-white/90",
      )}
    >
      {children}
    </button>
  );
}
