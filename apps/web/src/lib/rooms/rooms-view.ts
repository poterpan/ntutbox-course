/**
 * 教室課表頁（D25）的精簡資料結構：build 期把 v1 `rooms.json` 的課號對好 catalog 的課名／教師／
 * 課程頁連結，頁面與 client 元件只拿這份（client 不另抓 catalog）。純函式、好測。
 */
import { courseHref } from "../share/course-link";

/** 只取需要的欄位（v1 TermRoom / CourseOffering 的子集），測試好造。 */
export interface RawRoom {
  code: string;
  raw: string;
  full_name?: string | null;
  capacity?: number | null;
  slots?: { day: number; period: string; offering_ids?: string[] | null }[] | null;
  gis?: { building_id: string; floor_id?: string | null; class_number?: string | null }[] | null;
}

export interface RawCourse {
  offering_id: string;
  name?: { zh?: string | null } | null;
  teachers?: { name?: string | null }[] | null;
}

export interface RoomCourseRef {
  offeringId: string;
  /** 課名；catalog 查不到 → null（頁面改顯示課號） */
  name: string | null;
  teachers: string;
  /** 課程頁連結；catalog 查不到 → null（避免連到不存在的課） */
  href: string | null;
}

export interface RoomSlotView {
  day: number;
  period: string;
  courses: RoomCourseRef[];
}

export interface RoomView {
  code: string;
  raw: string;
  /** 顯示名：full_name，沒有就用 raw */
  name: string;
  capacity: number | null;
  buildingId: string | null;
  buildingName: string;
  floorId: string | null;
  slots: RoomSlotView[];
}

export const OTHER_BUILDING = "其他";

export function roomHref(code: string): string {
  return `/rooms/${encodeURIComponent(code)}/`;
}

export function buildRoomViews(
  termKey: string,
  rooms: readonly RawRoom[],
  courses: readonly RawCourse[],
  buildingNames: ReadonlyMap<string, string>,
): RoomView[] {
  const byId = new Map(courses.map((c) => [c.offering_id, c]));
  const ref = (id: string): RoomCourseRef => {
    const c = byId.get(id);
    if (!c) return { offeringId: id, name: null, teachers: "", href: null };
    return {
      offeringId: id,
      name: c.name?.zh?.trim() || null,
      teachers: (c.teachers ?? []).map((t) => t.name?.trim()).filter(Boolean).join("、"),
      href: courseHref({ termKey, offeringId: id }),
    };
  };
  return rooms.map((r) => {
    const g = r.gis?.[0] ?? null;
    const buildingId = g?.building_id ?? null;
    return {
      code: r.code,
      raw: r.raw,
      name: r.full_name?.trim() || r.raw,
      capacity: r.capacity ?? null,
      buildingId,
      // 大樓名稱查不到（GIS 快照讀不到）→ 退回 building_id，仍分得出組；只有完全沒有 GIS 才歸「其他」
      buildingName: buildingId ? buildingNames.get(buildingId) ?? buildingId : OTHER_BUILDING,
      floorId: g?.floor_id ?? null,
      slots: (r.slots ?? []).map((s) => ({
        day: s.day,
        period: s.period,
        courses: (s.offering_ids ?? []).map(ref),
      })),
    };
  });
}

export interface BuildingGroup<R> {
  buildingId: string | null;
  buildingName: string;
  rooms: R[];
}

/**
 * 依 GIS 大樓分組。大樓順序照 `buildingOrder`（GIS 快照順序），不在其中的依名稱；
 * 對不到 GIS（沒有 building_id）→「其他」，排最後。組內依 raw（教室短名）自然排序。
 */
export function groupRoomsByBuilding<R extends { buildingId: string | null; buildingName: string; raw: string }>(
  rooms: readonly R[],
  buildingOrder: readonly string[] = [],
): BuildingGroup<R>[] {
  const groups = new Map<string, BuildingGroup<R>>();
  for (const r of rooms) {
    const other = !r.buildingId;
    const key = other ? "\u0000other" : r.buildingId!;
    let g = groups.get(key);
    if (!g) {
      g = { buildingId: other ? null : r.buildingId, buildingName: other ? OTHER_BUILDING : r.buildingName, rooms: [] };
      groups.set(key, g);
    }
    g.rooms.push(r);
  }
  const rank = new Map(buildingOrder.map((id, i) => [id, i]));
  const collator = new Intl.Collator("zh-Hant", { numeric: true });
  const list = [...groups.values()];
  for (const g of list) g.rooms.sort((a, b) => collator.compare(a.raw, b.raw));
  return list.sort((a, b) => {
    if (a.buildingId === null) return 1;
    if (b.buildingId === null) return -1;
    const ra = rank.get(a.buildingId) ?? Infinity;
    const rb = rank.get(b.buildingId) ?? Infinity;
    if (ra !== rb) return ra - rb;
    return collator.compare(a.buildingName, b.buildingName);
  });
}
