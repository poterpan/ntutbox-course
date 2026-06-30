import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

/**
 * Solid accent action button (排入 / 送出 …). Previously hand-rolled in three
 * places with drifting size, radius, shadow and transition. `sm` is the
 * in-list action ("＋ 排入"); `lg` is the prominent drawer CTA.
 */
export const accentButtonVariants = cva(
  "inline-flex shrink-0 items-center justify-center bg-[var(--accent)] font-semibold text-white shadow-sm transition-[filter] hover:brightness-110 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      size: {
        sm: "h-7 rounded-lg px-3 text-xs",
        lg: "rounded-xl px-6 py-2.5 text-sm",
      },
    },
    defaultVariants: { size: "sm" },
  },
);

export function AccentButton({
  size,
  className,
  type = "button",
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof accentButtonVariants>) {
  return <button type={type} className={cn(accentButtonVariants({ size }), className)} {...props} />;
}
