import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function GlassBar({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass-surface rounded-t-2xl px-4 py-2", className)} {...props} />;
}
