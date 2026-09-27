"use client";
import { useEffect, useState } from "react";

/** 全 app 共用一次請求（module-level promise，避免同一頁多個元件重複發）。 */
let pending: Promise<string | null> | null = null;

function fetchHubTerm(): Promise<string | null> {
  pending ??= fetch("/hub-term.json")
    .then((r) => (r.ok ? (r.json() as Promise<{ termKey?: unknown }>) : null))
    .then((j) => (j && typeof j.termKey === "string" ? j.termKey : null))
    .catch(() => null);
  return pending;
}

/** 測試用：清掉快取。 */
export function __resetHubTermCache() {
  pending = null;
}

/**
 * `/browse/**` hub 建構時用的學期（build 期產的 /hub-term.json），未就緒 / 失敗回 null。
 *
 * 用途：判斷「現在看的學期是否就是 hub 的學期」。hub 頁只為那個學期的開課單位產生靜態頁
 * （`dynamicParams = false`），看其他學期時不該給系所 hub 連結——那個單位可能沒有 hub → 404。
 * hub 跟的是部署當下的預設學期（D21）；不在 client 端重算，因為部署後預設學期可能已切換，
 * 重算會對不上實際產出的 hub 頁。
 */
export function useHubTerm(): string | null {
  const [term, setTerm] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchHubTerm().then((t) => { if (alive) setTerm(t); });
    return () => { alive = false; };
  }, []);
  return term;
}
