/**
 * 課程頁的橫向交叉連結（同課其他班 / 同教師其他課 / 同單位其他課）。
 *
 * hub 頁解決的是「垂直」爬行路徑（首頁 → 系所 → 課程）；這裡解決「橫向」：
 * 讓 2,4xx 個課程頁彼此相連，形成連通圖而不是 2,4xx 條各自從 hub 垂下的斷頭路。
 * 對搜尋引擎的意義是多條發現路徑 + 權重可以在課程頁之間流動；對使用者的意義是
 * 「這門課還有別班嗎／這老師還開什麼」這兩個選課時最常問的問題就在頁面上。
 *
 * 資料全部現成（catalog 已在前端記憶體）：course_code（跨學期固定、同編碼＝同課多班）、
 * teachers[]、unit_code。不需要新的資料檔、不需要後端。
 *
 * 純函式、不碰 React：好測。
 */
import type { CourseOffering } from "@/lib/data/types";
import { cyclicWindow, scheduleLabel, teachersLabel } from "./units";

export interface RelatedRef {
  offeringId: string;
  name: string;
  teachers: string;
  /** 開課班級名（同課其他班最需要的辨識資訊） */
  classes: string;
  schedule: string;
  unitName: string;
  credits: string;
}

export interface RelatedGroup {
  /** 區塊標題 */
  title: string;
  /** 一句話說明這組是怎麼算出來的（誠實揭露判準，也是給使用者的線索） */
  hint: string;
  items: RelatedRef[];
}

/** 每組上限。合計 ≤ 22 條/頁——足以建圖，又不到會被視為連結農場的量級。 */
export interface RelatedLimits {
  sameCode: number;
  sameTeacher: number;
  sameUnit: number;
}

export const DEFAULT_RELATED_LIMITS: RelatedLimits = { sameCode: 8, sameTeacher: 6, sameUnit: 8 };

function toRef(c: CourseOffering): RelatedRef {
  return {
    offeringId: c.offering_id,
    name: c.name?.zh ?? c.offering_id,
    teachers: teachersLabel(c),
    classes: (c.classes ?? [])
      .map((k) => k?.name)
      .filter((n): n is string => !!n?.trim())
      .join("、"),
    schedule: scheduleLabel(c),
    unitName: c.unit_name ?? "",
    credits: c.credits != null ? String(c.credits) : "",
  };
}

/** 可當連結目標的課：非佔位課、非自己。 */
function linkable(c: CourseOffering, selfId: string): boolean {
  return !c.is_placeholder && c.offering_id !== selfId;
}

function sortById(list: CourseOffering[]): CourseOffering[] {
  return [...list].sort((a, b) => (a.offering_id < b.offering_id ? -1 : a.offering_id > b.offering_id ? 1 : 0));
}

/**
 * @param course 目前的課
 * @param all 同學期全部開課（catalog.courses）
 * @returns 三組交叉連結；每組已去重（同一堂課不會在兩組重複出現）、空組不回傳
 */
export function buildRelated(
  course: CourseOffering,
  all: readonly CourseOffering[],
  limits: RelatedLimits = DEFAULT_RELATED_LIMITS,
): RelatedGroup[] {
  const selfId = course.offering_id;
  const used = new Set<string>([selfId]);
  const groups: RelatedGroup[] = [];

  const take = (pool: CourseOffering[], limit: number) => {
    const fresh = pool.filter((c) => !used.has(c.offering_id));
    // 環狀取窗：以自己在 pool 中的位置為起點，保證同組每堂課收到的內部連結數一致
    // （見 units.ts cyclicWindow 的理由）。位置用課號排序後的 index，穩定可重現。
    const ordered = sortById(fresh);
    const anchor = ordered.findIndex((c) => c.offering_id > selfId);
    const picked = cyclicWindow(ordered, anchor < 0 ? 0 : anchor, limit);
    for (const c of picked) used.add(c.offering_id);
    return picked.map(toRef);
  };

  // ① 同課其他班：course_code 相同（跨學期固定的課程編碼；同編碼可對多課號＝多班）。
  if (course.course_code) {
    const items = take(
      all.filter((c) => linkable(c, selfId) && c.course_code === course.course_code),
      limits.sameCode,
    );
    if (items.length) {
      groups.push({
        title: "同課其他班",
        hint: `課程編碼 ${course.course_code} 的其他開課班次`,
        items,
      });
    }
  }

  // ② 同教師其他課：teachers 交集（用姓名比對——來源的 teacher code 有缺值，
  //    姓名是實際可比的鍵；同名不同人的風險存在，但這是連結而非事實斷言）。
  const names = new Set(
    (course.teachers ?? []).map((t) => t?.name?.trim()).filter((n): n is string => !!n),
  );
  if (names.size > 0) {
    const items = take(
      all.filter(
        (c) => linkable(c, selfId) && (c.teachers ?? []).some((t) => t?.name && names.has(t.name.trim())),
      ),
      limits.sameTeacher,
    );
    if (items.length) {
      groups.push({
        title: "同教師其他課",
        hint: `${[...names].join("、")} 在本學期開設的其他課程`,
        items,
      });
    }
  }

  // ③ 同單位其他課：同 unit_code。這組讓每堂課至少有一組橫向連結（unit_code 幾乎恆有值），
  //    是「沒有 course_code 兄弟班、也沒有掛教師」的課的保底路徑。
  if (course.unit_code) {
    const items = take(
      all.filter((c) => linkable(c, selfId) && c.unit_code === course.unit_code),
      limits.sameUnit,
    );
    if (items.length) {
      groups.push({
        title: `${course.unit_name ?? course.unit_code} 其他課程`,
        hint: "同開課單位的其他課程",
        items,
      });
    }
  }

  return groups;
}
