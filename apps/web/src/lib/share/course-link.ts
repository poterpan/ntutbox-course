// F-A 分享單堂課：連結編解碼（純函式，好測）。
// 格式：{origin}/?term=<term_key>&course=<offering_id>
// 用兩個明確參數，避免 term_key 內的 "-" 造成解析歧義。

export interface CourseLinkParams {
  termKey: string;
  offeringId: string;
}

export function buildCourseLink({
  termKey,
  offeringId,
  origin,
}: CourseLinkParams & { origin: string }): string {
  const p = new URLSearchParams({ term: termKey, course: offeringId });
  return `${origin}/?${p.toString()}`;
}

/** Parse a course share link. Accepts a URLSearchParams or a raw query string
 * (with or without leading "?"). Returns null unless both params are present. */
export function parseCourseLink(search: URLSearchParams | string): CourseLinkParams | null {
  const p = typeof search === "string" ? new URLSearchParams(search) : search;
  const termKey = p.get("term")?.trim();
  const offeringId = p.get("course")?.trim();
  if (!termKey || !offeringId) return null;
  return { termKey, offeringId };
}

/**
 * 站內相對連結（hub 頁與課程頁交叉連結用）。
 *
 * 與 buildCourseLink 同參數但不帶 origin：站內連結用相對路徑，本機 / preview 部署 /
 * 正式站都指得對，也不會把 origin 寫死進靜態 HTML。
 */
export function courseHref({ termKey, offeringId }: CourseLinkParams): string {
  const p = new URLSearchParams({ term: termKey, course: offeringId });
  return `/?${p.toString()}`;
}
