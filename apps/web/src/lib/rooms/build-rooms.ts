/**
 * **Build 期專用**的教室課表載入器（`/rooms/**`、`/rooms-index.json`、sitemap 用；D25）。
 * 為什麼在 build 期讀、資料來源與退路：同 `lib/hub/build-catalog.ts`——CDN 抓不到就退回 repo 內
 * fixtures（`public/data/v1`），不讓 CDN 短暫失聯擋下部署。
 *
 * 學期＝教室學期（`resolveRoomTerm`：本學期，沒有 rooms 才退回有 rooms 的最新學期），
 * **不是** hub 的預設學期。
 *
 * 大樓名稱：v1 rooms.json 只帶 `building_id`，名稱取自 repo 內 vendored 的 GIS 快照
 * （`crawler/ntut_catalog/reference/gis-rooms.json`，derive 對應用的同一份）。讀不到 → 退回
 * building_id 當名稱（仍分得出組），並告警。
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
  /** GIS 快照的大樓順序（分組排序用） */
  buildingOrder: string[];
}

const LOCAL_ROOT = path.join(process.cwd(), "public", "data", "v1");
const GIS_SNAPSHOT = path.join(process.cwd(), "..", "..", "crawler", "ntut_catalog", "reference", "gis-rooms.json");

async function readLocalJson<T>(rel: string): Promise<T> {
  return JSON.parse(await readFile(path.join(LOCAL_ROOT, rel), "utf8")) as T;
}

async function fetchJson<T>(base: string, rel: string): Promise<T> {
  const res = await fetch(`${base}/${rel}`);
  if (!res.ok) throw new Error(`${rel} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

async function loadBuildings(): Promise<{ names: Map<string, string>; order: string[] }> {
  try {
    const snap = JSON.parse(await readFile(GIS_SNAPSHOT, "utf8")) as {
      buildings?: { building_id: string; name?: string | null }[];
    };
    const list = snap.buildings ?? [];
    return {
      names: new Map(list.filter((b) => b.name).map((b) => [b.building_id, b.name!])),
      order: list.map((b) => b.building_id),
    };
  } catch (e) {
    console.warn(`[rooms] 讀不到 GIS 快照（${e instanceof Error ? e.message : e}），大樓名稱改用 building_id`);
    return { names: new Map(), order: [] };
  }
}

async function loadFrom(read: <T>(rel: string) => Promise<T>): Promise<RoomsCatalog> {
  const manifest = await read<Manifest>("manifest.json");
  const termKey = resolveRoomTerm(manifest, new Date());
  if (!termKey) throw new Error("manifest 沒有任何帶 rooms 的學期");
  const [rooms, catalog, periods, buildings] = await Promise.all([
    read<TermRooms>(`terms/${termKey}/rooms.json`),
    read<TermCatalog>(`terms/${termKey}/catalog.json`),
    read<PeriodTable>(`terms/${termKey}/periods.json`),
    loadBuildings(),
  ]);
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
