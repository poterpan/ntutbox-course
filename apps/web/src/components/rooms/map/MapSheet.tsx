"use client";
/**
 * 手機版地圖的底部面板（D27）：收合（只有摘要）／一半（這棟的教室）／展開，拖把手切換。
 * 只在地圖容器裡定位，不蓋住整頁；拖曳只綁在把手列，面板內容可以照常捲動、地圖手勢不受影響。
 */
import { useCallback, useRef, useState, type ReactNode } from "react";

export type SheetSnap = "peek" | "half" | "full";
const ORDER: SheetSnap[] = ["peek", "half", "full"];
const PEEK_PX = 92;

function heightFor(snap: SheetSnap, container: number): number {
  if (snap === "peek") return PEEK_PX;
  return Math.round(container * (snap === "half" ? 0.5 : 0.88));
}

export function MapSheet({
  snap,
  onSnap,
  containerHeight,
  header,
  children,
}: {
  snap: SheetSnap;
  onSnap: (s: SheetSnap) => void;
  containerHeight: number;
  header: ReactNode;
  children: ReactNode;
}) {
  const [drag, setDrag] = useState<number | null>(null); // 拖曳中的高度
  const start = useRef<{ y: number; h: number; t: number } | null>(null);
  const target = heightFor(snap, containerHeight);
  const height = drag ?? target;

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    start.current = { y: e.clientY, h: target, t: performance.now() };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!start.current) return;
    const h = start.current.h + (start.current.y - e.clientY);
    setDrag(Math.max(PEEK_PX, Math.min(heightFor("full", containerHeight), h)));
  };
  const finish = useCallback(
    (e: React.PointerEvent) => {
      const s = start.current;
      start.current = null;
      if (!s) return;
      const moved = s.y - e.clientY;
      const h = drag ?? s.h;
      setDrag(null);
      if (Math.abs(moved) < 6) {
        // 點一下把手：往上一段，最上面時收回
        const i = ORDER.indexOf(snap);
        onSnap(ORDER[i === ORDER.length - 1 ? 0 : i + 1]!);
        return;
      }
      const velocity = moved / Math.max(1, performance.now() - s.t); // px/ms，正＝往上
      const i = ORDER.indexOf(snap);
      if (velocity > 0.5) return onSnap(ORDER[Math.min(ORDER.length - 1, i + 1)]!);
      if (velocity < -0.5) return onSnap(ORDER[Math.max(0, i - 1)]!);
      // 慢慢拖：停在最近的那一段
      const nearest = ORDER.reduce((best, k) =>
        Math.abs(heightFor(k, containerHeight) - h) < Math.abs(heightFor(best, containerHeight) - h) ? k : best,
      );
      onSnap(nearest);
    },
    [containerHeight, drag, onSnap, snap],
  );

  return (
    <div
      className="absolute inset-x-0 bottom-0 z-20 flex flex-col rounded-t-3xl bg-white shadow-[0_-8px_30px_rgba(0,0,0,0.12)] ring-1 ring-black/[0.06] dark:bg-neutral-900 dark:ring-white/10"
      style={{ height, transition: drag === null ? "height 220ms cubic-bezier(.2,.8,.2,1)" : "none" }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-label={snap === "full" ? "收合面板" : "展開面板"}
        aria-expanded={snap !== "peek"}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={finish}
        onPointerCancel={finish}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            const i = ORDER.indexOf(snap);
            onSnap(ORDER[i === ORDER.length - 1 ? 0 : i + 1]!);
          }
        }}
        className="shrink-0 cursor-grab touch-none select-none px-4 pb-2 pt-2 active:cursor-grabbing"
      >
        <div className="mx-auto mb-2 h-1.5 w-10 rounded-full bg-black/15 dark:bg-white/25" />
        {header}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-4">{children}</div>
    </div>
  );
}

export const SHEET_PEEK_PX = PEEK_PX;
export { heightFor as sheetHeight };
