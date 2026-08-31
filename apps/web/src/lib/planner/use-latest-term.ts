"use client";
import { useEffect, useState } from "react";
import { getDataSource } from "@/lib/data";
import { latestTermKey } from "@/lib/share/course-sitemap";

/** 全 app 共用一次 manifest（TermSwitcher 也抓同一支 URL → 瀏覽器層是 cache hit；
 * 這裡再加一層 module-level promise，避免同一頁多個元件重複發請求）。 */
let pending: Promise<string | null> | null = null;

function fetchLatestTerm(): Promise<string | null> {
  pending ??= getDataSource()
    .getManifest()
    .then((m) => latestTermKey(Object.keys(m.terms ?? {})))
    .catch(() => null);
  return pending;
}

/** 測試用：清掉快取。 */
export function __resetLatestTermCache() {
  pending = null;
}

/**
 * 最新已發佈學期（manifest 推導），未就緒 / 失敗回 null。
 *
 * 用途：判斷「現在看的學期是否就是 `/browse/**` hub 建構時用的學期」。
 * hub 頁只為最新學期的開課單位產生靜態頁（`dynamicParams = false`），
 * 所以看舊學期時不該給系所 hub 連結——那個單位可能當年有、現在沒有 → 404。
 * 用 manifest 而不是寫死學期字串：新學期發佈後自動跟上，不需要改程式。
 */
export function useLatestTerm(): string | null {
  const [latest, setLatest] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchLatestTerm().then((t) => { if (alive) setLatest(t); });
    return () => { alive = false; };
  }, []);
  return latest;
}
