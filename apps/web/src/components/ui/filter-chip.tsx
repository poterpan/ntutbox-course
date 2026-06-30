import * as React from "react";
import { cva } from "class-variance-authority";

/**
 * The rounded pill toggle shared by the filter bar (時間 / 必修選修 / EMI) and
 * every FilterCombobox trigger. Previously this exact class string was inlined
 * in four places and drifted. Triggers that hold multiple children additionally
 * wrap with `inline-flex items-center gap-1.5`.
 */
export const filterChipVariants = cva(
  "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
  {
    variants: {
      active: {
        true: "border-transparent bg-[var(--accent)] text-white shadow-sm",
        false: "border-black/10 bg-white/70 text-[var(--ink)] hover:bg-white",
      },
    },
    defaultVariants: { active: false },
  },
);

/** Small count pill shown inside an active filter chip. */
export function CountBadge({ children }: { children: React.ReactNode }) {
  return (
    <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-white/25 px-1 text-[10px] font-bold text-white">
      {children}
    </span>
  );
}
