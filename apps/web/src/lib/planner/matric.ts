import type { CourseOffering, MatricSystem } from "@/lib/data/types";

// 學制（matric）解析：把課程的 matric 碼 → 精確中文標籤 + 使用者面粗分組。
//
// 單一真相在資料層（crawler/models.py 的 MATRIC_LABELS / select_matric_division）。
// 此處鏡像同一份對照，作為 **web fallback**：published 資料尚未帶第一級
// `matric_division` 時，從 `raw_fields.matric_codes` 推導（資料重發後自動走第一級欄位）。

/** 使用者面分組（學制感知用）。 */
export type MatricGroup = "day_ug" | "ext_ug" | "grad_day" | "grad_onjob" | "other";

const CODE_LABEL: Record<string, string> = {
  "5": "日五專", "6": "日二技", "7": "日四技", "8": "碩士", "9": "博士",
  "0": "進修學院二技", "4": "進修部二技", "F": "進修部四技",
  "A": "進修部碩士在職專班", "C": "週末碩士", "D": "EMBA",
  "1": "學程", "E": "學士後學位學程",
};

const CODE_SYSTEM: Record<string, MatricSystem> = {
  "5": "day", "6": "day", "7": "day", "8": "day", "9": "day",
  "0": "extension", "4": "extension", "F": "extension",
  "A": "on_job", "C": "on_job", "D": "on_job",
  "1": "other", "E": "other",
};

// 4 組對映：日間部大學(5/6/7) / 進修部大學(0/4/F) / 研究所·日間碩博(8/9) /
// 在職·週末·EMBA(A/C/D) / 其他·學程(1/E)。
// 在職與日間碩博「不同部制、預設不互修」(見 issue #17 查證) → 不併入研究所。
const CODE_GROUP: Record<string, MatricGroup> = {
  "5": "day_ug", "6": "day_ug", "7": "day_ug",
  "0": "ext_ug", "4": "ext_ug", "F": "ext_ug",
  "8": "grad_day", "9": "grad_day",
  "A": "grad_onjob", "C": "grad_onjob", "D": "grad_onjob",
  "1": "other", "E": "other",
};

/** 完整分組名（學制選擇器 / 圖例用）。 */
export const GROUP_LABEL: Record<MatricGroup, string> = {
  day_ug: "日間部", ext_ug: "進修部", grad_day: "研究所", grad_onjob: "在職·週末", other: "學程",
};

/** 列表徽章：短名 + 每組柔色（可一眼掃讀；避開課表用的藍/橘）。 */
export const GROUP_BADGE: Record<MatricGroup, { label: string; className: string }> = {
  day_ug: { label: "日間部", className: "bg-slate-100 text-slate-600" },
  ext_ug: { label: "進修部", className: "bg-amber-100 text-amber-700" },
  grad_day: { label: "研究所", className: "bg-emerald-100 text-emerald-700" },
  grad_onjob: { label: "在職", className: "bg-violet-100 text-violet-700" },
  other: { label: "學程", className: "bg-zinc-100 text-zinc-600" },
};

/** 學制選擇器可選的身分（學程/其他不列為身分；該類學生選「全部」）。 */
export const SELECTOR_GROUPS: MatricGroup[] = ["day_ug", "ext_ug", "grad_day", "grad_onjob"];

// 多碼裁定（與 models.py select_matric_division 一致）：體系優先 day>extension>on_job>other，
// 同體系取碼字典序最小；未知碼歸 other、不回退預設；已知碼優先於未知。
const SYSTEM_PRIORITY: MatricSystem[] = ["day", "extension", "on_job", "other"];

function pickCode(codes: string[]): string | null {
  const known = codes.filter((c) => c in CODE_SYSTEM);
  const unknown = codes.filter((c) => c && !(c in CODE_SYSTEM)).sort();
  if (known.length === 0) return unknown[0] ?? null;
  for (const sys of SYSTEM_PRIORITY) {
    const inSys = known.filter((c) => CODE_SYSTEM[c] === sys).sort();
    if (inSys.length) return inSys[0];
  }
  return [...known].sort()[0];
}

export interface MatricInfo {
  code: string;
  label: string;        // 精確學制（如「進修部碩士在職專班」）
  system: MatricSystem;
  group: MatricGroup;
}

/**
 * 解析課程的學制。優先用資料層第一級 `matric_division`（資料重發後）；
 * 否則回退從 `raw_fields.matric_codes` 推導。無 matric 碼 → null。
 */
export function resolveMatric(course: CourseOffering): MatricInfo | null {
  const md = course.matric_division;
  if (md?.code) {
    return {
      code: md.code,
      label: md.label || CODE_LABEL[md.code] || md.code,
      system: md.system ?? CODE_SYSTEM[md.code] ?? "other",
      group: CODE_GROUP[md.code] ?? "other",
    };
  }
  const raw = course.raw_fields?.["matric_codes"] ?? "";
  const codes = raw.split(",").map((s) => s.trim()).filter(Boolean);
  const code = pickCode(codes);
  if (!code) return null;
  return {
    code,
    label: CODE_LABEL[code] ?? code,
    system: CODE_SYSTEM[code] ?? "other",
    group: CODE_GROUP[code] ?? "other",
  };
}

/**
 * 課程庫徽章顯示規則（學制感知）：
 * - 未選學制（userGroup=null）→ 每門課都標自己的學制組（完整透明度）。
 * - 已選學制 → 只標「非本學制」的課（本學制不標，凸顯非自己體系的課）。
 */
export function libraryBadge(group: MatricGroup, userGroup: MatricGroup | null): { label: string; className: string } | null {
  if (userGroup != null && group === userGroup) return null;
  return GROUP_BADGE[group];
}
