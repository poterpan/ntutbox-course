"use client";
import { Input } from "@/components/ui/input";
import { useUiStore } from "@/store/ui-store";

export function CourseSearchBar() {
  const { query, setQuery } = useUiStore();
  return (
    <Input
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      placeholder="搜尋任何：課名 / 教師 / 課號 / 課程編碼…"
      aria-label="搜尋課程"
    />
  );
}
