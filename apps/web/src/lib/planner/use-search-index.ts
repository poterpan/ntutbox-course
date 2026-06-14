"use client";
import { useMemo } from "react";
import { useTermStore } from "@/store/term-store";
import { buildIndex } from "@/lib/search/build-index";

export function useSearchIndex() {
  const bundle = useTermStore((s) => s.bundle);
  return useMemo(() => buildIndex(bundle?.catalog.courses ?? []), [bundle]);
}
