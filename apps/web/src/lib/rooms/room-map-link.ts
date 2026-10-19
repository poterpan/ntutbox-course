/**
 * 教室頁 → 北科盒子地圖（map.ntutbox.com）的深連結。純函式。
 *
 * 地圖站的室內深連結是 `?b=<棟>&f=<層>&r=<門牌>`：載入就進到那棟、那層、選好那間（f 沒有 → 只選建築）。
 * 棟／層／門牌就是 v1 `gis[]`（同一份 ntutbox-campus 資料，地圖站點教室時也反過來用它連回本站教室頁）。
 * 一間教室對到多個空間時取第一個對到門牌的；只知道樓層 → 開到那層；只知道大樓 → 選建築；沒有 GIS → null。
 */
import type { RoomGisRef } from "./rooms-view";

export const MAP_ORIGIN = "https://map.ntutbox.com";

export function roomMapHref(gis: readonly RoomGisRef[]): string | null {
  const g = gis.find((x) => x.floorId && x.classNumber) ?? gis.find((x) => x.floorId) ?? gis[0];
  if (!g?.buildingId) return null;
  const q = new URLSearchParams({ b: g.buildingId });
  if (g.floorId) q.set("f", g.floorId);
  if (g.floorId && g.classNumber) q.set("r", g.classNumber);
  return `${MAP_ORIGIN}/?${q}`;
}
