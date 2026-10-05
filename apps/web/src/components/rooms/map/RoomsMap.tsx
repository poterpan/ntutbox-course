"use client";
/**
 * 教室地圖 Beta（D27）：@ntutbox/map 的 2.5D 樓層圖，依課表把教室著色。
 *
 * - 只在 client 載入（RoomsBrowser 以 next/dynamic ssr:false 引入），three.js 不進清單模式的 bundle。
 * - 地理資料由套件讀 cdn.ntutbox.com/campus/v1；課表狀態由這裡算（lib/rooms/rooms-occupancy）再推進引擎。
 * - 桌機：地圖＋右側面板；手機：地圖＋可拖動的底部面板（MapSheet）。面板列出「目前這棟」的教室，
 *   跨大樓搜尋交給清單模式。
 * - 語意一律「依課表」（D23）：沒排課 ≠ 保證空著。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import {
  campusCdnSource,
  createIndoorMap,
  floorRank,
  type BuildingConfig,
  type IndoorMap,
  type SelectedRoom,
  type ViewInfo,
} from "@ntutbox/map";
import "@ntutbox/map/style.css";
import type { PeriodsLike } from "@/lib/rooms/room-now";
import {
  occupancyAt,
  slotAt,
  slotNow,
  sortedPeriods,
  statusLine,
  STATUS_LABEL,
  type MapSlot,
  type RoomOccupancy,
} from "@/lib/rooms/rooms-occupancy";
import { roomHref } from "@/lib/rooms/rooms-view";
import { cn } from "@/lib/utils";
import { NativeSelect } from "@/components/ui/native-select";
import { useNow } from "../RoomTimetable";
import type { DirectoryGroup } from "../RoomsDirectory";
import { MapSheet, SHEET_PEEK_PX, sheetHeight, type SheetSnap } from "./MapSheet";

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];
const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];
const DOT: Record<string, string> = {
  free: "bg-emerald-500",
  soon: "bg-amber-400",
  busy: "bg-slate-400",
  unknown: "bg-slate-200 ring-1 ring-slate-300",
};

type Choice = { mode: "now" } | { mode: "pick"; day: number; period: string };

interface BuildingRoom {
  key: string; // 地圖空間鍵；floor_only 是 棟/層/?代碼
  floorId: string;
  record: RoomOccupancy;
}

function useIsDesktop(): boolean {
  // 這個元件只在 client 執行（ssr:false），可以直接讀 matchMedia，避免桌機先閃一下手機版面
  const [desktop, setDesktop] = useState(() => window.matchMedia("(min-width: 1024px)").matches);
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const update = () => setDesktop(mq.matches);
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return desktop;
}

function slotLabel(slot: MapSlot | null): string {
  if (!slot) return "";
  return `週${WEEKDAYS[slot.day]} 第 ${slot.period} 節${slot.nextDay ? "（明天）" : ""}`;
}

export function RoomsMap({
  groups,
  periods,
  onFallback,
}: {
  groups: DirectoryGroup[];
  periods: PeriodsLike;
  onFallback: () => void;
}) {
  const rooms = useMemo(() => groups.flatMap((g) => g.rooms), [groups]);
  const now = useNow();
  const [choice, setChoice] = useState<Choice>({ mode: "now" });
  const slot = useMemo<MapSlot | null>(() => {
    if (choice.mode === "pick") return slotAt(choice.day, choice.period, periods);
    return now ? slotNow(now, periods) : null;
  }, [choice, now, periods]);
  const occ = useMemo(() => (slot ? occupancyAt(rooms, periods, slot) : null), [rooms, periods, slot]);

  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<IndoorMap<RoomOccupancy> | null>(null);
  const occRef = useRef(occ);
  useEffect(() => {
    occRef.current = occ;
  }, [occ]);
  const [buildings, setBuildings] = useState<Record<string, BuildingConfig> | null>(null);
  const [view, setView] = useState<ViewInfo | null>(null);
  const [selected, setSelected] = useState<SelectedRoom<RoomOccupancy> | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [campusFocus, setCampusFocus] = useState<string | null>(null);
  const startedRef = useRef(false);
  const selectedKeyRef = useRef<string | null>(null);

  const isDesktop = useIsDesktop();
  const [snap, setSnap] = useState<SheetSnap>("peek");
  const [boxHeight, setBoxHeight] = useState(600);
  // 引擎取景時避開左上的大樓選單與手機的底部面板
  const insetsRef = useRef({ top: 56, bottom: 0 });
  useEffect(() => {
    insetsRef.current = { top: 56, bottom: isDesktop ? 0 : sheetHeight("peek", boxHeight) };
  }, [isDesktop, boxHeight]);

  // 地圖只建一次（等第一次算出狀態，才不會先畫一遍全灰再重建）。
  const ready = occ !== null;
  useEffect(() => {
    if (!ready || !containerRef.current) return;
    let cancelled = false;
    const source = campusCdnSource();
    source
      .load()
      .then(({ buildings: config }) => {
        if (cancelled || !containerRef.current) return;
        setBuildings(config);
        const current = occRef.current!;
        const first = bestBuilding(config, current.map) ?? Object.keys(config)[0]!;
        try {
          mapRef.current = createIndoorMap<RoomOccupancy>(containerRef.current, {
            source,
            buildings: config,
            occupancy: current.map,
            initialBuilding: first,
            initialView: "overview",
            getInsets: () => insetsRef.current,
            onViewChange: (info) => {
              startedRef.current = true;
              setView(info);
            },
            onRoomSelect: (room) => {
              setSelected(room);
              // 引擎換節次時會重送同一間的選取；只有選了「另一間」才把面板拉起來
              if (room && room.key !== selectedKeyRef.current) setSnap((s) => (s === "peek" ? "half" : s));
              selectedKeyRef.current = room?.key ?? null;
            },
            onNotice: (text) => setNotice(text),
            onCampusFocus: (focus) => setCampusFocus(focus?.buildingId ?? null),
            onError: (err) => {
              // 開場載不到＝整張地圖不能用；之後切大樓失敗只提示，原本的地圖還在
              if (err.type === "load-failed" || (err.type === "building-load-failed" && !startedRef.current)) {
                setFailure("地圖資料暫時載入不了，請稍後再試。");
              } else if (err.type === "building-load-failed") {
                setNotice("這棟的平面圖暫時載入不了，請稍後再試");
              }
            },
          });
        } catch {
          setFailure("這個瀏覽器無法顯示 3D 地圖（WebGL 不可用）。");
        }
      })
      .catch(() => {
        if (!cancelled) setFailure("地圖資料暫時載入不了，請稍後再試。");
      });
    return () => {
      cancelled = true;
      mapRef.current?.destroy();
      mapRef.current = null;
    };
  }, [ready]);

  // 顯示錯誤畫面時容器會被卸下：先停掉引擎的繪圖迴圈
  useEffect(() => {
    if (!failure) return;
    mapRef.current?.destroy();
    mapRef.current = null;
  }, [failure]);

  // 只知道樓層的教室沒有引擎的選取：離開那一層就收起卡片
  useEffect(() => {
    if (selected?.key.includes("/?") && (view?.building !== selected.buildingId || view?.floor !== selected.floorId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSelected(null);
    }
  }, [view, selected]);

  // 換節次：只重新上色，不重建
  useEffect(() => {
    if (occ) mapRef.current?.setOccupancy(occ.map);
  }, [occ]);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 2600);
    return () => clearTimeout(t);
  }, [notice]);

  useEffect(() => {
    const el = containerRef.current?.parentElement;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setBoxHeight(entry!.contentRect.height));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const buildingRooms = useMemo<BuildingRoom[]>(() => {
    if (!occ || !view) return [];
    const seen = new Set<string>();
    const list: BuildingRoom[] = [];
    for (const [key, record] of occ.map) {
      const [b, f] = key.split("/");
      if (b !== view.building || seen.has(record.code)) continue;
      seen.add(record.code);
      list.push({ key, floorId: f!, record });
    }
    const rank = { free: 0, soon: 1, busy: 2 } as const;
    return list.sort(
      (a, b) =>
        floorRank(a.floorId) - floorRank(b.floorId) ||
        rank[a.record.status] - rank[b.record.status] ||
        a.record.raw.localeCompare(b.record.raw, "zh-Hant", { numeric: true }),
    );
  }, [occ, view]);

  const shownRooms = view?.floor ? buildingRooms.filter((r) => r.floorId === view.floor) : buildingRooms;
  const available = shownRooms.filter((r) => r.record.status !== "busy").length;

  const focusRoom = useCallback(async (r: BuildingRoom) => {
    const map = mapRef.current;
    if (!map) return;
    if (r.key.includes("/?")) {
      // 只知道樓層：先飛到那層（換層會清掉引擎的選取），再顯示課表狀態卡片
      map.clearSelection();
      const ok = await map.setView({ building: r.key.split("/")[0], view: "floor", floor: r.floorId });
      if (!ok) return;
      selectedKeyRef.current = r.key;
      setSelected({
        key: r.key,
        buildingId: r.key.split("/")[0]!,
        buildingName: view?.buildingName ?? "",
        floorId: r.floorId,
        classNumber: "",
        gisName: "",
        status: r.record.status,
        occupancy: r.record,
      });
      return;
    }
    await map.selectRoom(r.key);
  }, [view?.buildingName]);

  const buildingOptions = useMemo(() => {
    if (!buildings || !occ) return [];
    const counts = new Map<string, { total: number; available: number }>();
    for (const [key, rec] of occ.map) {
      const b = key.split("/")[0]!;
      const c = counts.get(b) ?? { total: 0, available: 0 };
      c.total++;
      if (rec.status !== "busy") c.available++;
      counts.set(b, c);
    }
    // 名稱與順序跟清單模式一致（`groups`＝rooms.json `buildings` 的 label／order，D28）：
    // 只列有課程教室、且引擎進得去的大樓；「其他」（對不到 GIS）不列。
    return groups
      .filter((g) => g.key !== "other" && buildings[g.key])
      .map((g) => ({ id: g.key, name: g.buildingName, ...(counts.get(g.key) ?? { total: 0, available: 0 }) }));
  }, [buildings, occ, groups]);

  if (failure) {
    return (
      <div className="rounded-2xl bg-white/60 px-5 py-8 text-center ring-1 ring-black/[0.07] dark:bg-white/[0.05] dark:ring-white/10">
        <p className="text-sm text-[var(--ink)]">{failure}</p>
        <button type="button" onClick={onFallback} className="mt-3 text-sm font-semibold text-[var(--accent-ink)] hover:underline">
          改用清單
        </button>
      </div>
    );
  }

  const isCampus = view?.view === "campus";
  const go = (target: Parameters<IndoorMap<RoomOccupancy>["setView"]>[0]) => void mapRef.current?.setView(target);
  const crumb =
    "rounded px-0.5 font-semibold text-[var(--accent-ink)] hover:underline focus-visible:outline-2 focus-visible:outline-[var(--accent)]";
  // 面板頂端＝目前位置的麵包屑：上一層都能點回去（單層 → 全樓層 → 校園）。
  // 手機版在拖曳把手裡，按鈕要擋住 pointerdown，不然會被當成拖曳／點把手。
  const stop = (e: React.PointerEvent) => e.stopPropagation();
  const header = (
    <div className="flex items-baseline justify-between gap-2">
      <nav aria-label="地圖位置" className="flex min-w-0 items-baseline gap-1 truncate text-sm text-[var(--ink-soft)]">
        {!view ? (
          <span className="font-semibold text-[var(--ink)]">載入中…</span>
        ) : isCampus ? (
          <span className="font-semibold text-[var(--ink)]">北科校園</span>
        ) : (
          <>
            <button type="button" onPointerDown={stop} onClick={() => go({ view: "campus" })} className={crumb}>
              校園
            </button>
            <span aria-hidden>›</span>
            {view.floor ? (
              <>
                <button type="button" onPointerDown={stop} onClick={() => go({ building: view.building, view: "overview" })} className={crumb}>
                  {view.buildingShort ?? view.buildingName ?? view.building}
                </button>
                <span aria-hidden>›</span>
                <span className="font-semibold text-[var(--ink)]">{view.floor}</span>
              </>
            ) : (
              <span className="truncate font-semibold text-[var(--ink)]">{view.buildingShort ?? view.buildingName ?? view.building}</span>
            )}
          </>
        )}
      </nav>
      <p className="shrink-0 text-xs text-[var(--ink-soft)]">
        {isCampus
          ? campusTotals(buildingOptions)
          : view && shownRooms.length > 0
            ? `依課表 ${available}/${shownRooms.length} 間沒排課`
            : ""}
      </p>
    </div>
  );

  const panel = isCampus ? (
    <CampusPanel
      buildings={buildingOptions}
      focus={campusFocus}
      onPick={(id) => go({ building: id, view: "overview" })}
    />
  ) : (
    <RoomPanel
      selected={selected}
      rooms={shownRooms}
      floorView={!!view?.floor}
      onPick={(r) => void focusRoom(r)}
      onClose={() => {
        setSelected(null);
        mapRef.current?.clearSelection();
      }}
    />
  );

  return (
    <div>
      <SlotPicker periods={periods} choice={choice} slot={slot} onChange={setChoice} />

      <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_340px] lg:gap-4">
        <div className="relative h-[72dvh] overflow-hidden rounded-2xl bg-[#f0f2f6] ring-1 ring-black/[0.07] lg:h-[640px] dark:ring-white/10">
          {/* 引擎會在這個元素加上 .indoor-map（position: relative），所以用 h-full 撐滿，不能靠 absolute */}
          <div ref={containerRef} className="h-full w-full" />
          {buildingOptions.length > 0 && (
            <NativeSelect
              aria-label="切換大樓"
              containerClassName="absolute left-3 top-3 z-10 max-w-[60%]"
              value={view?.building ?? ""}
              onChange={(e) => void mapRef.current?.setView({ building: e.target.value, view: "overview" })}
              className="truncate rounded-xl bg-white/95 py-2 pl-3 text-sm font-semibold text-[var(--ink)] shadow-sm ring-1 ring-black/[0.08]"
            >
              {view?.building && !buildingOptions.some((b) => b.id === view.building) && (
                // 在地圖上點進沒有課程教室的大樓：補一個選項，選單才不會顯示成別棟
                <option value={view.building}>{view.buildingName ?? view.building}</option>
              )}
              {buildingOptions.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name}
                  {b.total ? `（${b.available} 間沒排課）` : ""}
                </option>
              ))}
            </NativeSelect>
          )}
          {notice && (
            <div className="pointer-events-none absolute inset-x-0 top-14 z-10 flex justify-center">
              <span className="rounded-full bg-black/75 px-3 py-1.5 text-xs text-white">{notice}</span>
            </div>
          )}
          {!isDesktop && (
            // 指北針預設貼底，會被收合的面板蓋住；往上移到面板之上（旋轉後才點得回北方）
            <style>{`.indoor-map .compass { bottom: ${SHEET_PEEK_PX + 18}px; }`}</style>
          )}
          {!isDesktop && (
            <MapSheet snap={snap} onSnap={setSnap} containerHeight={boxHeight} header={header}>
              {panel}
            </MapSheet>
          )}
        </div>
        {isDesktop && (
          <aside className="flex h-[640px] flex-col overflow-hidden rounded-2xl bg-white/70 ring-1 ring-black/[0.07] dark:bg-white/[0.05] dark:ring-white/10">
            <div className="shrink-0 border-b border-black/[0.06] px-4 py-3 dark:border-white/10">{header}</div>
            <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">{panel}</div>
          </aside>
        )}
      </div>

      <p className="mt-3 text-xs text-[var(--ink-soft)]">
        地圖依課表著色：綠＝這節沒排課，黃＝60 分鐘內有課，灰＝這節有課，淡灰＝排課系統沒有這間。沒排課不保證空著。
        拖曳平移、雙指縮放；放大樓層進入，縮小回到全樓層或校園。
      </p>
    </div>
  );
}

function bestBuilding(config: Record<string, BuildingConfig>, map: Map<string, RoomOccupancy>): string | null {
  const counts = new Map<string, number>();
  for (const [key, rec] of map) {
    const b = key.split("/")[0]!;
    if (config[b] && rec.status !== "busy") counts.set(b, (counts.get(b) ?? 0) + 1);
  }
  let best: string | null = null;
  for (const [b, n] of counts) if (!best || n > counts.get(best)!) best = b;
  return best;
}

interface BuildingOption {
  id: string;
  name: string;
  total: number;
  available: number;
}

function campusTotals(list: BuildingOption[]): string {
  const total = list.reduce((n, b) => n + b.total, 0);
  const free = list.reduce((n, b) => n + b.available, 0);
  return total ? `依課表 ${free}/${total} 間沒排課` : "";
}

/** 校園白模時的面板：各棟依課表的沒排課數，點了飛進那棟。順序固定、同清單模式（`groups`）；地圖上高亮的那棟只加底色，不移位置（學生靠位置找）。 */
function CampusPanel({
  buildings,
  focus,
  onPick,
}: {
  buildings: BuildingOption[];
  focus: string | null;
  onPick: (id: string) => void;
}) {
  const withRooms = buildings.filter((b) => b.total > 0);
  return (
    <div className="pt-1">
      <p className="pb-2 text-xs text-[var(--ink-soft)]">
        選一棟大樓，或在地圖上點大樓、放大進入。
      </p>
      <ul className="divide-y divide-black/[0.05] dark:divide-white/10">
        {withRooms.map((b) => (
          <li key={b.id}>
            <button
              type="button"
              onClick={() => onPick(b.id)}
              className={cn(
                "flex w-full items-center gap-2.5 py-2 text-left hover:bg-black/[0.03] dark:hover:bg-white/[0.04]",
                b.id === focus && "bg-[var(--accent)]/[0.06]",
              )}
            >
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--ink)]">{b.name}</span>
              <span className="shrink-0 text-xs text-[var(--ink-soft)]">
                {b.available}/{b.total} 間沒排課
              </span>
              <span aria-hidden className="text-[var(--ink-faint)]">›</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SlotPicker({
  periods,
  choice,
  slot,
  onChange,
}: {
  periods: PeriodsLike;
  choice: Choice;
  slot: MapSlot | null;
  onChange: (c: Choice) => void;
}) {
  const tokens = useMemo(() => sortedPeriods(periods), [periods]);
  const day = choice.mode === "pick" ? choice.day : slot?.day ?? 1;
  const period = choice.mode === "pick" ? choice.period : slot?.period ?? tokens[0]?.token ?? "1";
  const select =
    "rounded-lg bg-white py-1.5 pl-2.5 text-sm text-[var(--ink)] ring-1 ring-black/[0.08] dark:bg-white/10 dark:ring-white/15";
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
      <button
        type="button"
        aria-pressed={choice.mode === "now"}
        onClick={() => onChange({ mode: "now" })}
        className={cn(
          "rounded-lg px-3 py-1.5 font-semibold ring-1",
          choice.mode === "now"
            ? "bg-[var(--accent)] text-white ring-transparent"
            : "bg-white text-[var(--ink)] ring-black/[0.08] dark:bg-white/10 dark:ring-white/15",
        )}
      >
        現在
      </button>
      <NativeSelect
        aria-label="星期"
        className={select}
        value={day}
        onChange={(e) => onChange({ mode: "pick", day: Number(e.target.value), period })}
      >
        {DAY_ORDER.map((d) => (
          <option key={d} value={d}>
            週{WEEKDAYS[d]}
          </option>
        ))}
      </NativeSelect>
      <NativeSelect
        aria-label="節次"
        className={select}
        value={period}
        onChange={(e) => onChange({ mode: "pick", day, period: e.target.value })}
      >
        {tokens.map((p) => (
          <option key={p.token} value={p.token}>
            第 {p.token} 節 {p.startHm}
          </option>
        ))}
      </NativeSelect>
      <span className="text-xs text-[var(--ink-soft)]" aria-live="polite">
        {slot ? `依課表 · ${slotLabel(slot)}${choice.mode === "now" && !slot.inSession && !slot.nextDay ? "（下一節）" : ""}` : ""}
      </span>
    </div>
  );
}

function RoomPanel({
  selected,
  rooms,
  floorView,
  onPick,
  onClose,
}: {
  selected: SelectedRoom<RoomOccupancy> | null;
  rooms: BuildingRoom[];
  floorView: boolean;
  onPick: (r: BuildingRoom) => void;
  onClose: () => void;
}) {
  if (selected) {
    const rec = selected.occupancy;
    const kind = rec ? rec.status : "unknown";
    return (
      <div className="pt-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs text-[var(--ink-soft)]">
              {selected.buildingName} {selected.floorId}
            </p>
            <p className="truncate text-lg font-bold text-[var(--ink)]">{rec?.raw ?? selected.classNumber}</p>
          </div>
          <button type="button" onClick={onClose} className="shrink-0 text-sm font-medium text-[var(--accent-ink)] hover:underline">
            回到清單
          </button>
        </div>
        <p className="mt-2 flex items-center gap-2 text-sm text-[var(--ink)]">
          <span className={cn("inline-block size-2.5 rounded-full", DOT[kind])} />
          <span className="font-semibold">{STATUS_LABEL[kind]}</span>
          <span className="text-[var(--ink-soft)]">{rec ? statusLine(rec) : "排課系統沒有這間的課表"}</span>
        </p>
        {rec && (
          <p className="mt-1 text-xs text-[var(--ink-soft)]">
            {rec.name !== rec.raw ? `${rec.name} · ` : ""}代碼 {rec.code}
            {rec.capacity != null ? ` · ${rec.capacity} 人` : ""}
          </p>
        )}
        {rec && (
          <Link
            href={roomHref(rec.code)}
            className="mt-3 inline-block rounded-lg bg-[var(--accent)]/12 px-3 py-1.5 text-sm font-semibold text-[var(--accent-ink)] hover:bg-[var(--accent)]/20"
          >
            整週課表 →
          </Link>
        )}
      </div>
    );
  }

  if (rooms.length === 0) {
    return <p className="py-4 text-sm text-[var(--ink-soft)]">這裡沒有排課系統裡的教室。</p>;
  }

  return (
    <ul className="divide-y divide-black/[0.05] dark:divide-white/10">
      {rooms.map((r, i) => {
        const floorHeader = !floorView && (i === 0 || rooms[i - 1]!.floorId !== r.floorId);
        return (
          <li key={r.record.code}>
            {floorHeader && <p className="pb-1 pt-3 text-xs font-semibold text-[var(--ink-soft)]">{r.floorId}</p>}
            <button
              type="button"
              onClick={() => onPick(r)}
              className="flex w-full items-center gap-2.5 py-2 text-left hover:bg-black/[0.03] dark:hover:bg-white/[0.04]"
            >
              <span className={cn("inline-block size-2.5 shrink-0 rounded-full", DOT[r.record.status])} />
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-[var(--ink)]">{r.record.raw}</span>
              <span className="shrink-0 text-xs text-[var(--ink-soft)]">{statusLine(r.record)}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
