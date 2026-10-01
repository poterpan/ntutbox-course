/**
 * 課程詳情 → 教室頁的連結條件（D25）。純函式。
 *
 * 教室頁只為「教室學期」（build 期凍結）且 rooms.json 裡有的教室產生靜態頁（`dynamicParams = false`），
 * 其他學期或不在清單的教室連過去會 404 → 這時維持純文字。清單由 build 期產的 `/rooms-index.json` 提供。
 */
import { roomHref } from "./rooms-view";

export interface RoomsIndex {
  termKey: string;
  codes: ReadonlySet<string>;
}

export function roomLinkHref(
  code: string | null | undefined,
  courseTermKey: string | null | undefined,
  index: RoomsIndex | null | undefined,
): string | null {
  if (!code || !courseTermKey || !index) return null;
  if (index.termKey !== courseTermKey || !index.codes.has(code)) return null;
  return roomHref(code);
}
