"use client";
import { useCallback, useEffect, useState } from "react";
import { dataBaseUrl } from "@/lib/env";
import type { MicroProgramDirectory } from "@/lib/data/types";

// 微學程目錄每學期 lazy-fetch，模組層 cache 避免重複請求。
const cache = new Map<string, MicroProgramDirectory>();

// 併發首載去重。cache 只在 response 回來後才有值，所以同一畫面上並存的多個
// useMprograms（MicroProgramPane / MicroProgramList / CourseLibrary /
// FavoritesList / CourseDetailContent 共 5 處）在首載時會各發一次請求。
// 這裡讓它們共用同一個 in-flight promise；dev StrictMode 的重複掛載亦受益。
// 結算後移除，之後走 cache 快速路徑；失敗不寫 cache，retry() 才能真的重試。
const inflight = new Map<string, Promise<MicroProgramDirectory>>();

function load(termKey: string): Promise<MicroProgramDirectory> {
  const pending = inflight.get(termKey);
  if (pending) return pending;
  const p = fetch(`${dataBaseUrl()}/terms/${termKey}/mprograms.json`)
    .then((r) => {
      if (!r.ok) throw new Error(String(r.status));
      return r.json() as Promise<MicroProgramDirectory>;
    })
    .then((j) => {
      cache.set(termKey, j);
      return j;
    })
    .finally(() => {
      inflight.delete(termKey);
    });
  inflight.set(termKey, p);
  return p;
}

export function useMprograms(termKey: string | null) {
  const [data, setData] = useState<MicroProgramDirectory | null>(
    termKey ? cache.get(termKey) ?? null : null);
  const [error, setError] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!termKey) return;
    const hit = cache.get(termKey);
    let alive = true;
    // Data-fetch effect: hydrating from cache / resetting before the async fetch synchronously is
    // intentional (immediate cache hit, no stale flash on term switch); runs only on (termKey,
    // tick) change. React Compiler over-flags this — see CourseDetailContent for the same pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (hit) { setData(hit); setError(false); return; }
    setData(null); setError(false);
    load(termKey)
      .then((j) => { if (alive) setData(j); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [termKey, tick]);

  const retry = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading: !!termKey && !data && !error, retry };
}
