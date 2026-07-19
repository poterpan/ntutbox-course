"use client";
import { useUiStore } from "@/store/ui-store";
import { useTermStore } from "@/store/term-store";
import { useMprograms } from "@/lib/planner/use-mprograms";
import { MicroProgramList } from "./MicroProgramList";
import { MicroProgramDetail } from "./MicroProgramDetail";

// 微學程面板：選定學程碼 → 明細，否則 → 清單。
// 查無該 code（資料尚未載入 / 學程已下架）→ 清 selectedProgramCode 回列表，不卡空白。
export function MicroProgramPane() {
  const storeTermKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const termKey = storeTermKey ?? selectedTerm;
  const selectedProgramCode = useUiStore((s) => s.selectedProgramCode);
  const { data } = useMprograms(termKey);

  const program = selectedProgramCode
    ? data?.programs?.find((p) => p.code === selectedProgramCode)
    : undefined;

  return program ? <MicroProgramDetail program={program} /> : <MicroProgramList />;
}
