/**
 * **Build 期專用**的教室課表載入器（`/rooms/**`、`/rooms-index.json`、sitemap 用；D25）。
 * 為什麼在 build 期讀、資料來源與退路：同 `lib/hub/build-catalog.ts`——CDN 抓不到就退回 repo 內
 * fixtures（`public/data/v1`），不讓 CDN 短暫失聯擋下部署。
 *
 * 學期＝教室學期（`resolveRoomTerm`：本學期，沒有 rooms 才退回有 rooms 的最新學期），
 * **不是** hub 的預設學期。
 *
 * 大樓名稱與順序：v1 rooms.json 的 `buildings`（`[{building_id, label, order}]`，derive 從
 * canonical `gis/gis-rooms.json` 算出，D28——與教室對應、地圖引擎讀的是同一份 ntutbox-campus 資料）。
 * 名稱＝`label`（derive 已退回 GIS 名稱），再退回 building_id；順序＝陣列順序（已依 `order` 排好）。
 * 舊檔沒有 `buildings` → 名稱用 building_id、依代碼排序，並告警。
 *
 * ⚠️ 只能被 server component / metadata route 匯入（用到 node:fs）。
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import { dataBaseUrl, isLocalData } from "@/lib/env";
import type { Manifest, PeriodTable, TermCatalog, TermRooms } from "@/lib/data/types";
import { resolveRoomTerm } from "./room-term";
import { buildRoomViews, type RawRoom, type RoomView } from "./rooms-view";

export interface RoomsCatalog {
  termKey: string;
  /** manifest `terms[t].rooms.checked_at`（最後一次確認資料的時間）；舊 manifest 沒有 → null */
  checkedAt: string | null;
  periods: PeriodTable;
  rooms: RoomView[];
  /** 大樓順序（rooms.json `buildings`，分組排序用；沒有 → 空，退回依代碼） */
  buildingOrder: string[];
}

const LOCAL_ROOT = path.join(process.cwd(), "public", "data", "v1");

async function readLocalJson<T>(rel: string): Promise<T> {
  return JSON.parse(await readFile(path.join(LOCAL_ROOT, rel), "utf8")) as T;
}

async function fetchJson<T>(base: string, rel: string): Promise<T> {
  const res = await fetch(`${base}/${rel}`);
  if (!res.ok) throw new Error(`${rel} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

/** rooms.json `buildings` → 名稱表與順序（`label ?? building_id`；排序同 derive：有 order 的在前、再依代碼）。 */
export function buildingsFromRooms(
  rooms: Pick<TermRooms, "buildings">,
  termKey: string,
): { names: Map<string, string>; order: string[] } {
  const list = [...(rooms.buildings ?? [])];
  if (list.length === 0) {
    console.warn(`[rooms] ${termKey} rooms.json 沒有 buildings（derive 尚未更新？），大樓名稱改用 building_id、依代碼排序`);
    return { names: new Map(), order: [] };
  }
  list.sort((a, b) => {
    const oa = a.order ?? null;
    const ob = b.order ?? null;
    if (oa !== ob) {
      if (oa === null) return 1;
      if (ob === null) return -1;
      return oa - ob;
    }
    return a.building_id < b.building_id ? -1 : a.building_id > b.building_id ? 1 : 0;
  });
  return {
    names: new Map(list.map((b) => [b.building_id, b.label || b.building_id])),
    order: list.map((b) => b.building_id),
  };
}

async function loadFrom(read: <T>(rel: string) => Promise<T>): Promise<RoomsCatalog> {
  const manifest = await read<Manifest>("manifest.json");
  const termKey = resolveRoomTerm(manifest, new Date());
  if (!termKey) throw new Error("manifest 沒有任何帶 rooms 的學期");
  const [rooms, catalog, periods] = await Promise.all([
    read<TermRooms>(`terms/${termKey}/rooms.json`),
    read<TermCatalog>(`terms/${termKey}/catalog.json`),
    read<PeriodTable>(`terms/${termKey}/periods.json`),
  ]);
  const buildings = buildingsFromRooms(rooms, termKey);
  const list = (rooms.rooms ?? []) as unknown as RawRoom[];
  if (list.length === 0) throw new Error(`${termKey} rooms.json 沒有教室`);
  const entry = (manifest.terms?.[termKey] as { rooms?: { checked_at?: string | null } | null } | undefined)?.rooms;
  return {
    termKey,
    checkedAt: entry?.checked_at ?? null,
    periods,
    rooms: buildRoomViews(termKey, list, catalog.courses ?? [], buildings.names),
    buildingOrder: buildings.order,
  };
}

let cached: Promise<RoomsCatalog> | null = null;

/** 整個 build 只載入一次（索引 + 每間教室頁 + rooms-index.json + sitemap 共用）。 */
export function loadRoomsCatalog(): Promise<RoomsCatalog> {
  cached ??= (async () => {
    if (isLocalData()) return loadFrom(readLocalJson);
    const base = dataBaseUrl();
    try {
      return await loadFrom((rel) => fetchJson(base, rel));
    } catch (e) {
      console.warn(`[rooms] 從 ${base} 取資料失敗（${e instanceof Error ? e.message : e}），退回 repo 內 fixtures`);
      return loadFrom(readLocalJson);
    }
  })();
  return cached;
}
