"use client";
/**
 * `/rooms/` 的「清單｜地圖 Beta」切換（D27）。
 *
 * 初次 render（＝靜態 HTML）一律是清單：全部教室的 `<a>` 都在 HTML 裡（D25 的 SEO 前提不變）。
 * mount 後才讀 `?view=map` 或上次的選擇；地圖與 three.js 只在切到地圖時才下載（next/dynamic，ssr:false）。
 */
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { PeriodsLike } from "@/lib/rooms/room-now";
import { cn } from "@/lib/utils";
import { RoomsDirectory, type DirectoryGroup } from "./RoomsDirectory";

const RoomsMap = dynamic(() => import("./map/RoomsMap").then((m) => m.RoomsMap), {
  ssr: false,
  loading: () => (
    <div className="flex h-[70dvh] items-center justify-center rounded-2xl bg-white/60 text-sm text-[var(--ink-soft)] ring-1 ring-black/[0.07] lg:h-[640px] dark:bg-white/[0.05] dark:ring-white/10">
      載入地圖…
    </div>
  ),
});

type View = "list" | "map";
const STORAGE_KEY = "ntutbox-rooms-view";

function readStored(): View | null {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v === "map" || v === "list" ? v : null;
  } catch {
    return null;
  }
}

export function RoomsBrowser({ groups, periods }: { groups: DirectoryGroup[]; periods: PeriodsLike }) {
  const [view, setView] = useState<View>("list");

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("view");
    const initial = fromUrl === "map" || fromUrl === "list" ? fromUrl : readStored();
    // 刻意 mount 後才切：靜態 HTML 一律是清單（SEO），網址／上次的選擇只有瀏覽器知道
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (initial === "map") setView("map");
  }, []);

  const choose = (next: View) => {
    setView(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* 無痕模式等：不記住也沒關係 */
    }
    const url = new URL(window.location.href);
    if (next === "map") url.searchParams.set("view", "map");
    else url.searchParams.delete("view");
    window.history.replaceState(null, "", url);
  };

  return (
    <div>
      <div role="group" aria-label="檢視方式" className="mb-4 inline-flex rounded-xl bg-black/[0.05] p-1 dark:bg-white/10">
        {(["list", "map"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => choose(v)}
            className={cn(
              "rounded-lg px-3.5 py-1.5 text-sm font-semibold transition-colors",
              view === v
                ? "bg-white text-[var(--ink)] shadow-sm dark:bg-white/20"
                : "text-[var(--ink-soft)] hover:text-[var(--ink)]",
            )}
          >
            {v === "list" ? "清單" : (
              <>
                地圖<span className="ml-1 rounded bg-[var(--accent)]/15 px-1 py-px text-[10px] font-bold text-[var(--accent-ink)]">Beta</span>
              </>
            )}
          </button>
        ))}
      </div>
      {view === "map" ? (
        <RoomsMap groups={groups} periods={periods} onFallback={() => choose("list")} />
      ) : (
        <RoomsDirectory groups={groups} periods={periods} />
      )}
    </div>
  );
}
