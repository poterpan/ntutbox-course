// 廣告檔期歸因（§6）：只把 utm_campaign 對映成**固定 enum** 存 sessionStorage，
// 供 export_to_app_click 附帶。禁止保存原始 gclid、keyword 或完整 URL。

import type { CampaignKey } from "./events";
import { readSession, writeSession } from "./storage";

const STORAGE_KEY = "ntutbox_campaign_key";

/** utm_campaign 原值 → enum。未列入的 campaign 一律忽略（不自行造 key）。 */
const CAMPAIGN_KEYS: Record<string, CampaignKey> = {
  "1151_adddrop": "google_ads_1151",
};

const KNOWN: ReadonlySet<string> = new Set(Object.values(CAMPAIGN_KEYS));

/** 進站時呼叫一次：認得的 campaign 就記住，並回傳當前 campaign_key。 */
export function captureCampaignKey(search: string): CampaignKey | undefined {
  let raw: string | null = null;
  try {
    raw = new URLSearchParams(search).get("utm_campaign");
  } catch {
    raw = null;
  }
  const mapped = raw ? CAMPAIGN_KEYS[raw] : undefined;
  if (mapped) writeSession(STORAGE_KEY, mapped);
  return mapped ?? currentCampaignKey();
}

export function currentCampaignKey(): CampaignKey | undefined {
  const v = readSession(STORAGE_KEY);
  return v && KNOWN.has(v) ? (v as CampaignKey) : undefined;
}
