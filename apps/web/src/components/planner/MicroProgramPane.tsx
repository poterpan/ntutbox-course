"use client";
import { useUiStore } from "@/store/ui-store";
import { MicroProgramList } from "./MicroProgramList";

// 微學程面板：選定學程碼 → 明細（Task 13 的 MicroProgramDetail），否則 → 清單。
// 明細尚未實作，先放極簡 placeholder（Task 13 會替換）。
export function MicroProgramPane() {
  const selectedProgramCode = useUiStore((s) => s.selectedProgramCode);
  return selectedProgramCode ? (
    <div data-testid="mprogram-detail-placeholder" />
  ) : (
    <MicroProgramList />
  );
}
