/**
 * 系所 hub（`/browse/` 與 `/browse/<unit>/`）的純資料層。
 *
 * 為什麼需要 hub：SEO 稽核實測，sitemap 裡 2,4xx 個課程頁（`/?term=&course=`）
 * 內部連結數為 0——連首頁 `out/index.html` 都一個 `<a>` 都沒有（篩選器全是
 * `<button>`）。程式化頁面沒有爬行路徑等於孤島：搜尋引擎只能靠 sitemap 發現，
 * 權重也無法流動。hub 頁的唯一任務是把「首頁 → 系所 → 課程」這條路徑做出來，
 * 而且要做在**靜態 HTML 裡**（不是 client 渲染），連不執行 JS 的 AI 爬蟲都讀得到。
 *
 * 本檔刻意不碰 React / fs / fetch：純函式，好測。build 期的資料載入見 build-catalog.ts。
 */
import type { CourseOffering } from "@/lib/data/types";

/** hub 列表上一堂課要顯示的最小欄位（不整包塞 CourseOffering：靜態 HTML 會爆胖）。 */
export interface HubCourseRow {
  offeringId: string;
  name: string;
  credits: string;
  /** 修別符號（△▲等），來源沒有就空字串 */
  requirement: string;
  teachers: string;
  /** 「週一 3、4節；週三 5節」；無時段回 "" */
  schedule: string;
  /** 學制中文標籤（matric_division.label），無碼回 "" */
  division: string;
}

export interface UnitHub {
  /** URL segment（`/browse/<slug>/`） */
  slug: string;
  unitCode: string;
  unitName: string;
  courseCount: number;
  courses: HubCourseRow[];
}

/** 單位性質分組——`/browse/` 索引頁的分區標題。
 *
 * 為什麼不用現成的 `lib/filters/college-map.ts` 分學院：那份表只涵蓋 20 個 unit_code，
 * 實測 115-1 有 60 個單位、1,002/2,440 門課（41%）會落到「未分類」，而且表內有
 * 事實錯誤（`33` 標成車輛實為材資系、`40` 標成企管實為機電所、`61` 標成光電實為
 * 自動化所）。修那份表要動到既有「學院」篩選器的行為、且需要校方組織圖才能保證正確，
 * 屬於另一個議題。分組對爬行路徑毫無影響（純呈現），所以這裡改用**能從資料本身
 * 推導、不需要外部知識**的軸：單位中文名的尾綴。
 */
export type UnitKind = "dept" | "graduate" | "program" | "international" | "other";

export const UNIT_KIND_LABEL: Record<UnitKind, string> = {
  dept: "學系・科",
  graduate: "研究所",
  program: "學士班・學位學程",
  international: "外國學生專班",
  other: "學院・中心・其他單位",
};

/** `/browse/` 索引頁的分區順序。 */
export const UNIT_KIND_ORDER: UnitKind[] = ["dept", "graduate", "program", "international", "other"];

/** 由單位中文名尾綴判性質。純字串判斷、不假設校方組織圖。 */
export function unitKindOf(unitName: string): UnitKind {
  const n = unitName.trim();
  // 「專班」先判：名稱常同時含「外生／外國學生」與系所字樣（如「電資外國學生專班」）。
  if (/(外國學生|外生).*專班|專班$/.test(n)) return "international";
  if (/(學士班|學位學程|學程)$/.test(n)) return "program";
  if (/(所)$/.test(n)) return "graduate";
  if (/(系|科)$/.test(n)) return "dept";
  return "other";
}

const DAY = ["日", "一", "二", "三", "四", "五", "六"];

/** 「週一 3、4節；週三 5節」。與 CourseDetailContent 的呈現一致。 */
export function scheduleLabel(course: CourseOffering): string {
  return (course.meetings ?? [])
    .map((m) => `週${DAY[m.day] ?? m.day} ${(m.periods as string[]).join("、")}節`)
    .join("；");
}

export function teachersLabel(course: CourseOffering): string {
  return (course.teachers ?? [])
    .map((t) => t?.name)
    .filter((n): n is string => !!n?.trim())
    .join("、");
}

export function toHubRow(course: CourseOffering): HubCourseRow {
  return {
    offeringId: course.offering_id,
    name: course.name?.zh ?? course.offering_id,
    credits: course.credits != null ? String(course.credits) : "",
    requirement: course.requirement?.symbol ?? "",
    teachers: teachersLabel(course),
    schedule: scheduleLabel(course),
    division: course.matric_division?.label ?? "",
  };
}

/** unit_code → URL-safe slug。北科實測 unit_code 皆為 `[0-9A-Z]{2}`（如 `36`/`AA`/`2B`），
 * 但不寫死長度——未來多一碼也不該讓整個單位的 hub 消失。 */
export function unitSlug(unitCode: string): string {
  const s = unitCode.trim().toLowerCase().replace(/[^0-9a-z]+/g, "-").replace(/^-+|-+$/g, "");
  return s || "unknown";
}

/** 課程列的穩定排序：課號遞增。
 * 為什麼要「穩定」：靜態 HTML 每次 build 都應該一樣，否則每次部署整站 diff、
 * 也讓 Playwright/測試無法斷言。 */
function byOfferingId(a: CourseOffering, b: CourseOffering): number {
  return a.offering_id < b.offering_id ? -1 : a.offering_id > b.offering_id ? 1 : 0;
}

/**
 * 依 unit_code 分組成 hub。
 *
 * - 無 unit_code 的課程會落到 `unknown` hub（**不丟棄**：丟了就等於那些課永遠沒有
 *   內部連結，正是本次要修的問題）。
 * - `is_placeholder`（「請選…」佔位課、無師資 credit 0）**排除**：那不是可修的課，
 *   連過去是死連結體驗，對爬蟲也是薄內容。
 * - slug 撞名時後綴序號，保證 `/browse/<slug>/` 一對一。
 */
export function buildUnitHubs(courses: readonly CourseOffering[]): UnitHub[] {
  const groups = new Map<string, { unitName: string; courses: CourseOffering[] }>();
  for (const c of courses) {
    if (c.is_placeholder) continue;
    const code = c.unit_code?.trim() || "unknown";
    const g = groups.get(code) ?? { unitName: c.unit_name?.trim() || code, courses: [] };
    // 同 unit_code 的 unit_name 實測一致；若不一致取第一個非空值，不做猜測。
    if (!g.unitName && c.unit_name) g.unitName = c.unit_name.trim();
    g.courses.push(c);
    groups.set(code, g);
  }

  const seen = new Set<string>();
  return [...groups.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([unitCode, g]) => {
      let slug = unitSlug(unitCode);
      if (seen.has(slug)) {
        let i = 2;
        while (seen.has(`${slug}-${i}`)) i += 1;
        slug = `${slug}-${i}`;
      }
      seen.add(slug);
      const sorted = [...g.courses].sort(byOfferingId);
      return {
        slug,
        unitCode,
        unitName: g.unitName,
        courseCount: sorted.length,
        courses: sorted.map(toHubRow),
      };
    });
}

export interface UnitKindSection {
  kind: UnitKind;
  label: string;
  units: UnitHub[];
}

/** `/browse/` 索引頁分區：性質分組、組內依課程數遞減（大單位先曝光）。空組不出。 */
export function groupUnitsByKind(hubs: readonly UnitHub[]): UnitKindSection[] {
  const byKind = new Map<UnitKind, UnitHub[]>();
  for (const h of hubs) {
    const k = unitKindOf(h.unitName);
    const arr = byKind.get(k) ?? [];
    arr.push(h);
    byKind.set(k, arr);
  }
  return UNIT_KIND_ORDER.filter((k) => (byKind.get(k)?.length ?? 0) > 0).map((kind) => ({
    kind,
    label: UNIT_KIND_LABEL[kind],
    units: [...(byKind.get(kind) ?? [])].sort(
      (a, b) => b.courseCount - a.courseCount || (a.unitName < b.unitName ? -1 : 1),
    ),
  }));
}

/** 同一分區內的其他單位——unit hub 底部的橫向連結，讓爬蟲能在 hub 之間平移，
 * 不必每次回到 `/browse/`。 */
export function siblingUnits(hubs: readonly UnitHub[], slug: string, limit = 12): UnitHub[] {
  const self = hubs.find((h) => h.slug === slug);
  if (!self) return [];
  const kind = unitKindOf(self.unitName);
  const pool = hubs.filter((h) => h.slug !== slug && unitKindOf(h.unitName) === kind);
  return cyclicWindow(pool, hubs.indexOf(self), limit);
}

/**
 * 從 `from` 之後開始、環狀取 `limit` 個。
 *
 * 為什麼是環狀而不是「取前 N 個」：取前 N 個會讓排序在前的項目吃下全部內部連結、
 * 排序在後的一條都拿不到（正是要修的孤島問題換個形式再現一次）。環狀取窗讓
 * **每個項目收到的內部連結數相同**，且整組形成一個連通環——任何一點出發都走得完。
 */
export function cyclicWindow<T>(pool: readonly T[], startAfter: number, limit: number): T[] {
  if (pool.length === 0 || limit <= 0) return [];
  const n = pool.length;
  const base = ((startAfter % n) + n) % n;
  const out: T[] = [];
  for (let i = 0; i < Math.min(limit, n); i += 1) out.push(pool[(base + i) % n]);
  return out;
}
