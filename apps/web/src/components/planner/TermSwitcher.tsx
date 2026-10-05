"use client";
import { useEffect } from "react";
import { useTermStore } from "@/store/term-store";
import { useTermBootstrap } from "@/lib/planner/use-term-bootstrap";
import { useTermOptions } from "@/lib/terms/use-resolved-terms";
import { useUiStore } from "@/store/ui-store";
import { AccentButton } from "@/components/ui/accent-button";
import { cn } from "@/lib/utils";
import { NativeSelect } from "@/components/ui/native-select";

export function TermSwitcher() {
  const termKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const setSelectedTerm = useUiStore((s) => s.setSelectedTerm);
  const { terms, default: defaultTerm } = useTermOptions();
  useTermBootstrap(selectedTerm);

  // 預設學期（D21）：manifest 到手時若還沒有人指定學期（分享連結會在掛載時先指定）才套用。
  // 手動切換不跨次保存——每次進站都回到預設學期。
  useEffect(() => {
    if (defaultTerm && useUiStore.getState().selectedTerm === null) setSelectedTerm(defaultTerm);
  }, [defaultTerm, setSelectedTerm]);

  const shown = termKey ?? selectedTerm;
  const options = terms.length ? terms : shown ? [shown] : [];

  return (
    <div className="flex items-center gap-1.5">
      <NativeSelect
        className="rounded-md border bg-white/70 px-2 py-1 text-sm"
        value={shown ?? ""}
        onChange={(e) => setSelectedTerm(e.target.value)}
        aria-label="選擇學期"
        disabled={!options.length}
      >
        {options.length === 0 && <option value="">載入中…</option>}
        {options.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </NativeSelect>
      {/* 窄機 header 已塞滿（390px 實測），按鈕改由 PlannerLayout 在 header 下方另起一列 */}
      <BackToCurrentTerm className="hidden sm:inline-flex" />
    </div>
  );
}

/** 「回到本學期（115-1）」：檢視中的學期 ≠ 本學期時才出現（D21）；本學期沒有 catalog → 不出現。 */
export function BackToCurrentTerm({ className }: { className?: string }) {
  const termKey = useTermStore((s) => s.termKey);
  const selectedTerm = useUiStore((s) => s.selectedTerm);
  const setSelectedTerm = useUiStore((s) => s.setSelectedTerm);
  const { current } = useTermOptions();
  const shown = termKey ?? selectedTerm;
  if (!current || !shown || shown === current) return null;
  return (
    <AccentButton
      tone="soft"
      className={cn("text-[var(--accent-ink)]", className)}
      onClick={() => setSelectedTerm(current)}
      aria-label={`回到本學期（${current}）`}
    >
      回到本學期（{current}）
    </AccentButton>
  );
}
