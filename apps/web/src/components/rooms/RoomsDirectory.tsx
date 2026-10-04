"use client";
/**
 * `/rooms/` 的教室清單（D25）：依大樓分組＋client 端搜尋＋「目前沒排課」開關。
 *
 * 初次 render（＝靜態 HTML）不套任何篩選 → 全部教室的 `<a>` 都在 HTML 裡，爬蟲看得到。
 * 「目前沒排課」要知道現在幾點，mount 後才可用；非上課節次（第一節前、最後一節後）停用並說明。
 * 節間歸下一節，與教室頁的「現在」同一套規則（roomNow）。
 */
import { useMemo, useState } from "react";
import Link from "next/link";
import { SearchInput } from "@/components/ui/search-input";
import { filterChipVariants } from "@/components/ui/filter-chip";
import { roomNow, type PeriodsLike } from "@/lib/rooms/room-now";
import { roomHref, type RoomGisRef } from "@/lib/rooms/rooms-view";
import { cn } from "@/lib/utils";
import { useNow } from "./RoomTimetable";

export interface DirectoryRoom {
  code: string;
  name: string;
  raw: string;
  capacity: number | null;
  slotCount: number;
  /** `${day}-${period}`，判斷「目前沒排課」用 */
  slotKeys: string[];
  /** 地圖（D27）用：GIS 對應與比對方式 */
  gis: RoomGisRef[];
  gisMatch: string | null;
}

export interface DirectoryGroup {
  key: string;
  buildingName: string;
  rooms: DirectoryRoom[];
}

function matches(r: DirectoryRoom, building: string, q: string): boolean {
  if (!q) return true;
  return [r.name, r.raw, r.code, building].some((s) => s.toLowerCase().includes(q));
}

export function RoomsDirectory({ groups, periods }: { groups: DirectoryGroup[]; periods: PeriodsLike }) {
  const [query, setQuery] = useState("");
  const [freeOnly, setFreeOnly] = useState(false);
  const now = useNow();
  const current = useMemo(() => (now ? roomNow(now, periods, []) : null), [now, periods]);
  const activeKey = current?.active ? `${current.today}-${current.active.period}` : null;
  const freeEnabled = activeKey !== null;
  const applyFree = freeOnly && freeEnabled;

  const q = query.trim().toLowerCase();
  const filtered = useMemo(
    () =>
      groups
        .map((g) => ({
          ...g,
          rooms: g.rooms.filter(
            (r) => matches(r, g.buildingName, q) && (!applyFree || !r.slotKeys.includes(activeKey!)),
          ),
        }))
        .filter((g) => g.rooms.length > 0),
    [groups, q, applyFree, activeKey],
  );
  const total = groups.reduce((n, g) => n + g.rooms.length, 0);
  const shown = filtered.reduce((n, g) => n + g.rooms.length, 0);

  return (
    <div>
      <div className="mb-5 flex flex-col gap-2.5 sm:flex-row sm:items-center">
        <SearchInput
          aria-label="搜尋教室"
          placeholder="搜尋教室名稱、代碼或大樓，例如 共同312"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          containerClassName="flex-1"
        />
        <button
          type="button"
          aria-pressed={applyFree}
          disabled={!freeEnabled}
          onClick={() => setFreeOnly((v) => !v)}
          className={cn(
            filterChipVariants({ active: applyFree }),
            // 共用 chip 尚無深色樣式（#42）；這裡補上未選取態，避免白底白字
            !applyFree && "dark:border-white/15 dark:bg-white/10 dark:hover:bg-white/15",
            "shrink-0 self-start sm:self-auto disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          目前沒排課
          {current?.active && (
            <span className="font-medium opacity-80">
              （第 {current.active.period} 節）
            </span>
          )}
        </button>
      </div>
      <p className="-mt-3 mb-5 text-xs text-[var(--ink-soft)]" aria-live="polite">
        {now && !freeEnabled
          ? "現在不是上課節次，「目前沒排課」暫時停用。"
          : applyFree
            ? `第 ${current!.active!.period} 節依課表沒排課的教室 ${shown} 間（不保證空著）。`
            : q
              ? `符合的教室 ${shown} 間，共 ${total} 間。`
              : `共 ${total} 間教室。`}
      </p>

      {filtered.length === 0 && (
        <p className="rounded-xl bg-white/60 px-4 py-6 text-center text-sm text-[var(--ink-soft)] ring-1 ring-black/[0.07] dark:bg-white/[0.05] dark:ring-white/10">
          沒有符合的教室。
        </p>
      )}

      {filtered.map((g) => (
        <section key={g.key} className="mb-8">
          <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--ink-soft)]">{g.buildingName}</h2>
          <p className="mb-3 text-xs text-[var(--ink-faint)]">{g.rooms.length} 間</p>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {g.rooms.map((r) => (
              <li key={r.code}>
                <Link
                  href={roomHref(r.code)}
                  className="flex items-center gap-2 rounded-xl bg-white px-3 py-2.5 ring-1 ring-black/[0.07] transition-colors hover:bg-[var(--accent)]/[0.06] hover:ring-[var(--accent)]/30 dark:bg-white/[0.06] dark:ring-white/10"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-[var(--ink)]">{r.raw}</span>
                    <span className="block truncate text-[11px] text-[var(--ink-soft)]">
                      {r.name !== r.raw ? `${r.name} · ` : ""}代碼 {r.code}
                      {r.capacity != null ? ` · ${r.capacity} 人` : ""}
                    </span>
                  </span>
                  <span className="shrink-0 rounded-md bg-[var(--accent)]/12 px-1.5 py-0.5 text-[10px] font-bold tabular-nums text-[var(--accent-ink)]">
                    本週 {r.slotCount} 節
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
