"use client";
import { useEffect, useState } from "react";
import type { RoomsIndex } from "./room-link";

/** 全 app 共用一次請求（同 use-hub-term）。 */
let pending: Promise<RoomsIndex | null> | null = null;

function fetchRoomsIndex(): Promise<RoomsIndex | null> {
  pending ??= fetch("/rooms-index.json")
    .then((r) => (r.ok ? (r.json() as Promise<{ termKey?: unknown; codes?: unknown }>) : null))
    .then((j) =>
      j && typeof j.termKey === "string" && Array.isArray(j.codes)
        ? { termKey: j.termKey, codes: new Set(j.codes.filter((c): c is string => typeof c === "string")) }
        : null,
    )
    .catch(() => null);
  return pending;
}

/** 測試用：清掉快取。 */
export function __resetRoomsIndexCache() {
  pending = null;
}

/**
 * build 期產的教室頁清單（`/rooms-index.json`：教室學期＋有頁面的教室代碼），未就緒／失敗回 null。
 * 不在 client 端重算教室學期：部署後學期可能已切換，重算會對不上實際產出的頁面。
 */
export function useRoomsIndex(): RoomsIndex | null {
  const [index, setIndex] = useState<RoomsIndex | null>(null);
  useEffect(() => {
    let alive = true;
    void fetchRoomsIndex().then((i) => { if (alive) setIndex(i); });
    return () => { alive = false; };
  }, []);
  return index;
}
