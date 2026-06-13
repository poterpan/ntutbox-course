import { cn } from "@/lib/utils";
import type { HTMLAttributes } from "react";

export function GlassPanel({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("glass-surface rounded-2xl", className)} {...props} />;
}
