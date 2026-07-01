import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Accent action button (排入 / 已排 / 送出 …). Previously hand-rolled in several
 * places with drifting size, radius, shadow and padding. `size` controls the
 * footprint; `tone` the emphasis — both tones share identical size tokens so a
 * control that toggles between them (e.g. 排入 ⇄ 已排) never changes dimensions.
 * A transparent border on `solid` keeps its box identical to `soft`'s bordered box.
 */
export const accentButtonVariants = cva(
  "inline-flex shrink-0 items-center justify-center border font-semibold disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      tone: {
        solid:
          "border-transparent bg-[var(--accent)] text-white shadow-sm transition-[filter] hover:brightness-110",
        soft:
          "border-[var(--accent)]/30 bg-[var(--accent)]/10 text-[var(--accent)] transition-colors hover:bg-[var(--accent)]/20",
      },
      size: {
        sm: "h-7 rounded-lg px-3 text-xs",
        lg: "rounded-xl px-6 py-2.5 text-sm",
      },
    },
    defaultVariants: { tone: "solid", size: "sm" },
  },
);

export function AccentButton({
  tone,
  size,
  className,
  type = "button",
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof accentButtonVariants>) {
  return <button type={type} className={cn(accentButtonVariants({ tone, size }), className)} {...props} />;
}
