/**
 * 本學期／預設學期的判定（D21）。純函式、不依賴 React 與 `@/` 別名——
 * planner（client）、hub（build 期）、worker（sitemap，執行期）共用同一份規則。
 *
 * - **current（本學期）**：manifest `term_schedule.current` 已生效的最後一筆；各學期的開始日由 derive
 *   依行事曆 `administrative_start` 決定（沒有 → 8/1／2/1）。這裡不自己推日期；只有舊 manifest 沒有
 *   `term_schedule`（或沒有已生效項目）時才退回 `containingTerm` 的固定 8/1、2/1 規則。
 * - **default（網站預設顯示的學期）**：本學期；但從本學期的期中撤選截止起改為下學期。
 *   切換時刻由 derive 從行事曆推導、寫進 manifest 的 `term_schedule`（crawler/ntut_catalog/term_schedule.py）。
 *
 * 退路（依序）：預設學期不在 `manifest.terms`（還沒有 catalog）→ 本學期；本學期也不在 → `terms` 最新者。
 * 舊 manifest 沒有 `term_schedule` → 預設＝`terms` 最新者（與 D21 之前的行為相同），本學期照日期規則算。
 */
import { latestTermKey } from "../share/course-sitemap";

export interface TermScheduleEntryLike {
  term: string;
  from: string;
}

/** 只取判定需要的欄位，worker 解析出來的 JSON 也能直接傳。 */
export interface ManifestLike {
  terms?: Record<string, unknown> | null;
  term_schedule?: {
    current?: TermScheduleEntryLike[] | null;
    default?: TermScheduleEntryLike[] | null;
  } | null;
}

export interface ResolvedTerms {
  /** 本學期；不在 manifest.terms（沒有 catalog 可看）時為 null——此時不提供「回到本學期」。 */
  current: string | null;
  /** 網站預設顯示的學期；manifest 沒有任何學期時為 null。 */
  default: string | null;
}

const TAIPEI_OFFSET_MS = 8 * 60 * 60 * 1000;

/** 日期所在的學期（台北時間，固定 8/1、2/1），與 crawler `_containing_term` 同一條規則。僅作退路。 */
export function containingTerm(now: Date): string {
  const t = new Date(now.getTime() + TAIPEI_OFFSET_MS); // 以 UTC getter 讀台北的年月
  const year = t.getUTCFullYear();
  const month = t.getUTCMonth() + 1;
  if (month >= 8) return `${year - 1911}-1`;
  if (month === 1) return `${year - 1912}-1`;
  return `${year - 1912}-2`;
}

/** 時間軸上 `from ≤ now` 的最後一筆；沒有任何一筆生效 → null。 */
export function termAt(entries: TermScheduleEntryLike[] | null | undefined, now: Date): string | null {
  let best: string | null = null;
  let bestAt = -Infinity;
  const t = now.getTime();
  for (const e of entries ?? []) {
    const at = Date.parse(e.from);
    if (Number.isNaN(at) || at > t) continue;
    if (at >= bestAt) {
      bestAt = at;
      best = e.term;
    }
  }
  return best;
}

export function resolveTerms(manifest: ManifestLike | null | undefined, now: Date): ResolvedTerms {
  const available = Object.keys(manifest?.terms ?? {});
  const has = (t: string | null): t is string => t !== null && available.includes(t);
  const schedule = manifest?.term_schedule;

  const currentRaw = termAt(schedule?.current, now) ?? containingTerm(now);
  const current = has(currentRaw) ? currentRaw : null;

  if (!schedule) {
    return { current, default: latestTermKey(available) };
  }
  const defaultRaw = termAt(schedule.default, now) ?? currentRaw;
  const def = has(defaultRaw) ? defaultRaw : current ?? latestTermKey(available);
  return { current, default: def };
}
