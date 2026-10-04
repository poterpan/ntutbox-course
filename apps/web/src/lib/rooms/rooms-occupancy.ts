/**
 * 教室地圖（D27）的「依課表」狀態：某一節每間教室是 沒排課／快有課／有課，並算出「沒排課到幾點」「有課到幾點」。
 * 純函式；「現在」只在 client mount 後算（同 room-now.ts）。語意沿用 D23：沒排課 ≠ 保證空著。
 *
 * 輸出的 key 是地圖用的空間鍵 `棟/層/門牌`（@ntutbox/map 的 occupancy 鍵）。只知道樓層的教室（floor_only）
 * 用 `棟/層/?代碼`：地圖會算進樓層統計但沒有多邊形可以上色。building_only／none 放不上地圖，進 `unplaced`。
 */
import { zonedDayMinute, type PeriodsLike } from "./room-now";
import type { RoomGisRef } from "./rooms-view";

export type MapRoomStatus = "free" | "soon" | "busy";

/** 地圖需要的教室資料（`DirectoryRoom` 的子集，測試好造）。 */
export interface MapRoomInput {
  code: string;
  raw: string;
  name: string;
  capacity: number | null;
  gis: RoomGisRef[];
  gisMatch: string | null;
  /** `${day}-${period}` */
  slotKeys: string[];
}

export interface RoomOccupancy {
  status: MapRoomStatus;
  code: string;
  raw: string;
  name: string;
  capacity: number | null;
  /** free／soon：下一堂開始的 HH:MM；今天之後沒排課 → null */
  freeUntil: string | null;
  /** busy：連堂結束的 HH:MM */
  busyUntil: string | null;
}

/** 某一天的某一節。`refMinute` 是判斷「快有課」的基準時刻（現在，或該節開始）。 */
export interface MapSlot {
  day: number;
  period: string;
  refMinute: number;
  /** true＝現在正在這節；false＝節間歸下一節、跳到明天，或使用者選的節次 */
  inSession: boolean;
  /** 「現在」已過最後一節，改看明天第一節 */
  nextDay: boolean;
}

/** 下一堂在這麼多分鐘內開始 → 快有課（黃）。 */
export const SOON_MINUTES = 60;

interface Period {
  token: string;
  start: number;
  end: number;
  startHm: string;
  endHm: string;
}

function hm(s: string): number {
  const [h, m] = s.split(":").map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

export function sortedPeriods(periods: PeriodsLike): Period[] {
  return [...(periods.periods ?? [])]
    .sort((a, b) => a.order - b.order)
    .map((p) => ({ token: p.token, start: hm(p.start_hm), end: hm(p.end_hm), startHm: p.start_hm, endHm: p.end_hm }));
}

/**
 * 「現在」對應哪一節：節內 → 該節；節間 → 下一節；最後一節之後 → 明天第一節。
 * 與 room-now.ts 不同處：沒有 active 時不回 null，因為地圖總要畫某一節。
 */
export function slotNow(now: Date, periods: PeriodsLike): MapSlot | null {
  const list = sortedPeriods(periods);
  if (!list.length) return null;
  const { day, minute } = zonedDayMinute(now, periods.timezone ?? "Asia/Taipei");
  const inside = list.find((p) => p.start <= minute && minute < p.end);
  if (inside) return { day, period: inside.token, refMinute: minute, inSession: true, nextDay: false };
  const next = list.find((p) => p.start > minute);
  if (next) return { day, period: next.token, refMinute: minute, inSession: false, nextDay: false };
  const first = list[0]!;
  return { day: (day + 1) % 7, period: first.token, refMinute: first.start, inSession: false, nextDay: true };
}

/** 使用者選的節次：以該節開始時刻判斷「快有課」。 */
export function slotAt(day: number, period: string, periods: PeriodsLike): MapSlot | null {
  const p = sortedPeriods(periods).find((x) => x.token === period);
  return p ? { day, period, refMinute: p.start, inSession: false, nextDay: false } : null;
}

function statusAt(
  busy: ReadonlySet<string>,
  list: readonly Period[],
  slot: MapSlot,
): Pick<RoomOccupancy, "status" | "freeUntil" | "busyUntil"> {
  const idx = list.findIndex((p) => p.token === slot.period);
  if (busy.has(slot.period)) {
    let last = idx;
    while (last + 1 < list.length && busy.has(list[last + 1]!.token)) last++;
    return { status: "busy", freeUntil: null, busyUntil: list[last]!.endHm };
  }
  const next = list.slice(idx + 1).find((p) => busy.has(p.token));
  if (!next) return { status: "free", freeUntil: null, busyUntil: null };
  return {
    status: next.start - slot.refMinute <= SOON_MINUTES ? "soon" : "free",
    freeUntil: next.startHm,
    busyUntil: null,
  };
}

export interface OccupancyResult {
  /** 地圖空間鍵 → 狀態 */
  map: Map<string, RoomOccupancy>;
  /** 代碼 → 狀態（清單／卡片用，包含放不上地圖的教室） */
  byCode: Map<string, RoomOccupancy>;
  /** 地圖上放不了的教室代碼 */
  unplaced: string[];
}

export function occupancyAt(rooms: readonly MapRoomInput[], periods: PeriodsLike, slot: MapSlot): OccupancyResult {
  const list = sortedPeriods(periods);
  const map = new Map<string, RoomOccupancy>();
  const byCode = new Map<string, RoomOccupancy>();
  const unplaced: string[] = [];
  const prefix = `${slot.day}-`;
  for (const room of rooms) {
    const busy = new Set(room.slotKeys.filter((k) => k.startsWith(prefix)).map((k) => k.slice(prefix.length)));
    const record: RoomOccupancy = {
      code: room.code,
      raw: room.raw,
      name: room.name,
      capacity: room.capacity,
      ...statusAt(busy, list, slot),
    };
    byCode.set(room.code, record);
    let placed = false;
    for (const g of room.gis) {
      if (!g.floorId) continue;
      if (g.classNumber && (room.gisMatch === "rule" || room.gisMatch === "override")) {
        map.set(`${g.buildingId}/${g.floorId}/${g.classNumber}`, record);
        placed = true;
      } else if (room.gisMatch === "floor_only") {
        map.set(`${g.buildingId}/${g.floorId}/?${room.code}`, record);
        placed = true;
      }
    }
    if (!placed) unplaced.push(room.code);
  }
  return { map, byCode, unplaced };
}

/** 卡片上的一句話（「依課表」語意）。 */
export function statusLine(r: Pick<RoomOccupancy, "status" | "freeUntil" | "busyUntil">): string {
  if (r.status === "busy") return r.busyUntil ? `有課到 ${r.busyUntil}` : "這節有課";
  if (r.status === "soon") return `${r.freeUntil} 有課`;
  return r.freeUntil ? `沒排課到 ${r.freeUntil}` : "這天沒有再排課";
}

export const STATUS_LABEL: Record<MapRoomStatus | "unknown", string> = {
  free: "這節沒排課",
  soon: "快有課",
  busy: "這節有課",
  unknown: "無課表資料",
};
