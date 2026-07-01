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
