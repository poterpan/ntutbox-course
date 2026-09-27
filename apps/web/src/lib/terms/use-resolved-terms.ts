"use client";
import { useEffect, useState } from "react";
import { getDataSource } from "@/lib/data";
import { resolveTerms, type ResolvedTerms } from "./term-schedule";

export interface TermOptions extends ResolvedTerms {
  /** manifest 裡有 catalog 的學期（新→舊）；manifest 未就緒時為空陣列。 */
  terms: string[];
  ready: boolean;
}

const EMPTY: TermOptions = { terms: [], current: null, default: null, ready: false };

/** 全 app 共用一次 manifest 請求（module-level promise）；判定時刻＝manifest 到手的當下。 */
let pending: Promise<TermOptions> | null = null;

export function fetchTermOptions(): Promise<TermOptions> {
  pending ??= getDataSource()
    .getManifest()
    .then((m) => ({
      ...resolveTerms(m, new Date()),
      terms: Object.keys(m.terms ?? {}).sort().reverse(),
      ready: true,
    }))
    .catch(() => {
      pending = null; // 失敗不快取，下次掛載再試
      return EMPTY;
    });
  return pending;
}

/** 測試用：清掉快取。 */
export function __resetTermOptionsCache() {
  pending = null;
}

/** 學期清單＋本學期＋預設學期（D21）。 */
export function useTermOptions(): TermOptions {
  const [opts, setOpts] = useState<TermOptions>(EMPTY);
  useEffect(() => {
    let alive = true;
    void fetchTermOptions().then((o) => { if (alive) setOpts(o); });
    return () => { alive = false; };
  }, []);
  return opts;
}
