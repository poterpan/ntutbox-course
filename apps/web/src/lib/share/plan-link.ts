// F-B 分享整份課表：連結編解碼（純函式，好測）。
// 格式：{origin}/?term=<term_key>&plan=<offering_id.offering_id.…>
// 志願序用「順序」隱含（第 1 個 = 志願 1），故只存 offering_id。

export interface PlanLinkParams {
  termKey: string;
  offeringIds: string[];
}

export function buildPlanLink({
  termKey,
  offeringIds,
  origin,
}: PlanLinkParams & { origin: string }): string {
  const p = new URLSearchParams({ term: termKey, plan: offeringIds.join(".") });
  return `${origin}/?${p.toString()}`;
}

export function parsePlanLink(search: URLSearchParams | string): PlanLinkParams | null {
  const p = typeof search === "string" ? new URLSearchParams(search) : search;
  const termKey = p.get("term")?.trim();
  const plan = p.get("plan")?.trim();
  if (!termKey || !plan) return null;
  const offeringIds = plan.split(".").map((s) => s.trim()).filter(Boolean);
  if (offeringIds.length === 0) return null;
  return { termKey, offeringIds };
}
