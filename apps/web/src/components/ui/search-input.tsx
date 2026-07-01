"use client";
import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Shared search field for the planner. Centralises the bits that used to drift
 * across the three hand-rolled copies (CourseLibrary / SlotPopover /
 * FilterCombobox): 16px value (so iOS doesn't auto-zoom on focus), the
 * placeholder treatment (14px + --ink-faint/75) and the accent focus ring.
 * Per-placement chrome (bg / radius / padding) lives in `variant`.
 */
const VARIANT = {
  // CourseLibrary 課程庫主搜尋：白底、較大、實心 2px focus ring，帶放大鏡 icon
  prominent:
    "rounded-xl bg-white py-2.5 pl-9 pr-3 shadow-sm ring-1 ring-black/10 focus:ring-2 focus:ring-[var(--accent)] md:text-sm",
  // SlotPopover 對話框內：淡灰嵌入式
  inset:
    "rounded-lg bg-black/[0.04] px-3 py-2 ring-1 ring-black/5 focus:ring-[var(--accent)]/40 md:text-sm",
  // FilterCombobox 下拉內：半透明、最小，桌機 12px
  popover:
    "rounded-lg bg-white/70 px-2.5 py-1.5 ring-1 ring-black/5 focus:ring-[var(--accent)]/40 md:text-xs md:placeholder:text-xs",
} as const;

export interface SearchInputProps extends React.ComponentProps<"input"> {
  variant?: keyof typeof VARIANT;
  /** Show the leading magnifier icon. Defaults to on for `prominent` only. */
  withIcon?: boolean;
  /** className for the wrapper element (only rendered when an icon is shown). */
  containerClassName?: string;
}

export function SearchInput({
  variant = "prominent",
  withIcon,
  className,
  containerClassName,
  ...props
}: SearchInputProps) {
  const icon = withIcon ?? variant === "prominent";
  const field = (
    <input
      className={cn(
        "w-full text-base text-[var(--ink)] outline-none placeholder:text-sm placeholder:text-[var(--ink-faint)]/75",
        VARIANT[variant],
        className,
      )}
      {...props}
    />
  );
  if (!icon) return field;
  return (
    <div className={cn("relative", containerClassName)}>
      <svg
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--ink-soft)]"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        aria-hidden
      >
        <circle cx="11" cy="11" r="7" />
        <path d="m21 21-4.3-4.3" strokeLinecap="round" />
      </svg>
      {field}
    </div>
  );
}
