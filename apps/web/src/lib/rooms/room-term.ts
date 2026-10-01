/**
 * 教室課表頁（D25）的學期：**本學期**，不是 hub 的預設學期。
 *
 * 期中撤選截止後預設學期已切到下學期（D21），但教室裡上的仍是本學期的課。
 * 本學期沒有 rooms（還沒爬到、或 manifest 不認得本學期）→ 退回 manifest 中有 rooms 的最新學期。
 * 純函式、不依賴 `@/` 別名，build 期與測試共用。
 */
import { latestTermKey } from "../share/course-sitemap";
import { resolveTerms, type ManifestLike } from "../terms/term-schedule";

function hasRooms(manifest: ManifestLike | null | undefined, term: string): boolean {
  const entry = (manifest?.terms ?? {})[term] as { rooms?: unknown } | null | undefined;
  return entry?.rooms != null;
}

export function resolveRoomTerm(manifest: ManifestLike | null | undefined, now: Date): string | null {
  const { current } = resolveTerms(manifest, now);
  if (current && hasRooms(manifest, current)) return current;
  const withRooms = Object.keys(manifest?.terms ?? {}).filter((t) => hasRooms(manifest, t));
  return latestTermKey(withRooms);
}
