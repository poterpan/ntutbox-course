/**
 * **Build 期專用**的 catalog 載入器（`/browse/**` 的 server component 與 sitemap 用）。
 *
 * 為什麼要在 build 期讀資料：hub 頁的全部價值在於「靜態 HTML 裡就有真實 `<a>`」。
 * 若照全站慣例在 client 抓 catalog 再渲染，產出的 HTML 又是空殼——不執行 JS 的
 * AI 爬蟲（GPTBot / ClaudeBot / PerplexityBot）一條連結都看不到，等於沒做。
 * `output: "export"` 完全支援在 build 期跑 server component 與 generateStaticParams，
 * 所以這是可行且標準的做法。
 *
 * ⚠️ 只能被 server component / metadata route 匯入（用到 node:fs）。
 * 匯入到 client component 會在 bundle 階段炸開——這是刻意的護欄。
 *
 * 資料來源沿用既有 env 契約（lib/env.ts）：
 * - `NEXT_PUBLIC_DATA_BASE_URL` 未設（dev 預設 `/data/v1`）→ 讀本機 `public/data/v1`
 * - 設為 CDN URL（prod）→ build 期 HTTP 抓最新資料，抓不到就退回 repo 內已 commit 的
 *   fixtures。**不讓 CDN 短暫失聯把部署整條擋下**，退回的也是真資料（只是可能舊一版）。
 *
 * 已知限制（誠實記錄）：hub 頁的課程清單凍結在「最後一次部署」的資料。新學期發佈但
 * 沒有 code 部署時，hub 仍列上一學期——連結不會壞（課程頁吃任何 term），只是不夠新。
 * 要即時就得讓 publish pipeline 觸發部署，或改由 worker 動態產（見下方 rejected 註記）。
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import { dataBaseUrl, isLocalData } from "@/lib/env";
import { latestTermKey } from "@/lib/share/course-sitemap";
import type { CourseOffering, Manifest, TermCatalog } from "@/lib/data/types";

export interface HubCatalog {
  termKey: string;
  courses: CourseOffering[];
}

/** repo 內已 commit 的 fixtures（.gitignore 明確 un-ignore 了這個目錄）。 */
const LOCAL_ROOT = path.join(process.cwd(), "public", "data", "v1");

async function readLocalJson<T>(rel: string): Promise<T> {
  return JSON.parse(await readFile(path.join(LOCAL_ROOT, rel), "utf8")) as T;
}

async function fetchJson<T>(base: string, rel: string): Promise<T> {
  const res = await fetch(`${base}/${rel}`);
  if (!res.ok) throw new Error(`${rel} → HTTP ${res.status}`);
  return (await res.json()) as T;
}

async function loadFrom(read: <T>(rel: string) => Promise<T>): Promise<HubCatalog> {
  const manifest = await read<Manifest>("manifest.json");
  const termKey = latestTermKey(Object.keys(manifest.terms ?? {}));
  if (!termKey) throw new Error("manifest 沒有任何 term");
  const catalog = await read<TermCatalog>(`terms/${termKey}/catalog.json`);
  const courses = catalog.courses ?? [];
  if (courses.length === 0) throw new Error(`${termKey} catalog 沒有課程`);
  return { termKey, courses };
}

let cached: Promise<HubCatalog> | null = null;

/** 整個 build 只載入一次（`/browse/` + 60 個 unit hub + sitemap 共用同一份）。 */
export function loadHubCatalog(): Promise<HubCatalog> {
  cached ??= (async () => {
    if (isLocalData()) return loadFrom(readLocalJson);
    const base = dataBaseUrl();
    try {
      return await loadFrom((rel) => fetchJson(base, rel));
    } catch (e) {
      console.warn(`[hub] 從 ${base} 取資料失敗（${e instanceof Error ? e.message : e}），退回 repo 內 fixtures`);
      return loadFrom(readLocalJson);
    }
  })();
  return cached;
}
