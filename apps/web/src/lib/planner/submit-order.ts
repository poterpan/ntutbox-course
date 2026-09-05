// 全站唯一的「送出順序」規則。分享連結、學分卡、匯出 payload 都吃這個函式，
// 這樣「網頁看到的順序」＝「App 看到的順序」＝「未來送出的順序」三處對得起來。
//
// 規則：每個衝堂連通分量內 priority 最小者是第一志願（tier 1），其餘是備選（tier 2）；
// 第一志願段在前、備選段在後，兩段內各自保持排課站的 priority 升序；最後重編為連續 1..N。
// 衝堂本身交由學校選課系統裁定——我們只決定送件順序。

import { conflictGroups } from "@/lib/schedule/conflict";
import type { CourseOffering } from "@/lib/data/types";
import type { PlacedCourse } from "@/store/draft-store";

export interface OrderedCourse {
  offeringId: string;
  /** 連續 1..N。刻意不沿用 draft-store 的 priority——那個允許空洞，不該外流。 */
  priority: number;
  /** 1 = 第一志願、2 = 衝堂備選 */
  tier: 1 | 2;
}

export function submitOrder(
  placed: PlacedCourse[],
  byId: (id: string) => CourseOffering | undefined,
): OrderedCourse[] {
  // 先剔除當期 catalog 查不到的課號（跨學期殘留），否則重編號會留下空洞
  const valid = placed.filter((p) => byId(p.offering_id) !== undefined);
  if (valid.length === 0) return [];

  const priorityOf = new Map(valid.map((p) => [p.offering_id, p.priority]));
  const byPriority = (a: string, b: string) => priorityOf.get(a)! - priorityOf.get(b)!;

  const winners: string[] = [];
  const losers: string[] = [];
  for (const group of conflictGroups(valid.map((p) => p.offering_id), byId)) {
    const sorted = [...group].sort(byPriority);
    winners.push(sorted[0]);
    losers.push(...sorted.slice(1));
  }
  winners.sort(byPriority);
  losers.sort(byPriority);

  const winnerSet = new Set(winners);
  return [...winners, ...losers].map((offeringId, i) => ({
    offeringId,
    priority: i + 1,
    tier: winnerSet.has(offeringId) ? 1 : 2,
  }));
}
