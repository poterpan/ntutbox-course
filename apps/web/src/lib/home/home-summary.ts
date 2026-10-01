/**
 * 首頁靜態介紹區（`components/home/HomeIntro.tsx`）的 build 期資料：本學期數據＋熱門系所連結。
 *
 * 為什麼要有：首頁本體是 client 端排課器，靜態 HTML 只有載入中字樣與篩選標籤（約 216 字、
 * 2 個 `<a>`）。介紹區在 build 期就把說明文字、入口與系所 hub 連結寫進 HTML，
 * 不執行 JS 的爬蟲也讀得到，也讓首頁連到 `/rooms/`。
 *
 * 純函式（不碰 fs / fetch / React），好測；資料由 page.tsx 以 loadHubCatalog／loadRoomsCatalog 帶入。
 */
import type { CourseOffering } from "@/lib/data/types";
import { formatTaipeiDateTime } from "@/lib/format-time";
import { buildUnitHubs } from "@/lib/hub/units";

export interface HomeUnitLink {
  slug: string;
  unitName: string;
  courseCount: number;
}

export interface HomeSummary {
  /** hub 的預設學期（與 /browse/ 同一個，D21） */
  termKey: string;
  /** 不含佔位課（同 /browse/ 的計數） */
  courseCount: number;
  unitCount: number;
  /** 教室學期（本學期，可能與 termKey 不同：期中撤選截止後 hub 已換下學期）；沒有教室資料 → null */
  roomTermKey: string | null;
  roomCount: number | null;
  /** 「YYYY-MM-DD HH:mm」台北時間；沒有時間 → null（不顯示，不捏造） */
  updatedAt: string | null;
  /** 依課程數遞減的熱門系所（同數依名稱） */
  topUnits: HomeUnitLink[];
}

export interface HomeSummaryInput {
  hub: { termKey: string; courses: readonly CourseOffering[]; checkedAt: string | null };
  /** 教室資料載入失敗時傳 null：首頁不該因為教室資料缺席而 build 失敗 */
  rooms: { termKey: string; rooms: readonly unknown[] } | null;
  topN?: number;
}

export const HOME_TOP_UNITS = 12;

export function buildHomeSummary({ hub, rooms, topN = HOME_TOP_UNITS }: HomeSummaryInput): HomeSummary {
  const hubs = buildUnitHubs(hub.courses);
  const topUnits = [...hubs]
    .sort((a, b) => b.courseCount - a.courseCount || (a.unitName < b.unitName ? -1 : a.unitName > b.unitName ? 1 : 0))
    .slice(0, Math.max(0, topN))
    .map(({ slug, unitName, courseCount }) => ({ slug, unitName, courseCount }));
  return {
    termKey: hub.termKey,
    courseCount: hubs.reduce((n, h) => n + h.courseCount, 0),
    unitCount: hubs.length,
    roomTermKey: rooms?.termKey ?? null,
    roomCount: rooms ? rooms.rooms.length : null,
    updatedAt: formatTaipeiDateTime(hub.checkedAt),
    topUnits,
  };
}
