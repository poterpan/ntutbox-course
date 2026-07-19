"use client";
import { useCallback, useEffect, useState } from "react";
import { dataBaseUrl } from "@/lib/env";
import type { MicroProgramDirectory } from "@/lib/data/types";

// 微學程目錄每學期 lazy-fetch，模組層 cache 避免重複請求。
const cache = new Map<string, MicroProgramDirectory>();

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
    fetch(`${dataBaseUrl()}/terms/${termKey}/mprograms.json`)
      .then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then((j: MicroProgramDirectory) => { cache.set(termKey, j); if (alive) setData(j); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [termKey, tick]);

  const retry = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading: !!termKey && !data && !error, retry };
}
