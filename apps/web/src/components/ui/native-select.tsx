import * as React from "react";
import { ChevronDownIcon } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * 原生 `<select>` 加上一致的展開箭頭。瀏覽器內建的箭頭貼在右緣、也不吃 padding；
 * 這裡關掉它（appearance-none），自己畫一個並留出右側空間。外觀（底色、圓角、字級）照舊由 className 決定，
 * 版面相關的放在 `containerClassName`（例如 absolute 定位、寬度上限）。
 */
export interface NativeSelectProps extends React.ComponentProps<"select"> {
  containerClassName?: string;
}

export function NativeSelect({ className, containerClassName, children, ...props }: NativeSelectProps) {
  return (
    <span className={cn("relative inline-flex", containerClassName)}>
      <select className={cn("w-full appearance-none", className, "pr-8")} {...props}>
        {children}
      </select>
      <ChevronDownIcon
        aria-hidden
        className="pointer-events-none absolute right-2.5 top-1/2 size-4 -translate-y-1/2 text-[var(--ink-soft)]"
      />
    </span>
  );
}
