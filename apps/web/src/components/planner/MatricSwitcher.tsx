"use client";
import { useIdentityStore } from "@/store/identity-store";
import { SELECTOR_GROUPS, GROUP_LABEL, type MatricGroup } from "@/lib/planner/matric";

// 學制選擇器（header，學期右側）。選了學制 → 課程庫標出「非本學制」、
// 空格可選課程預設只顯本學制。未選 = 全部。
export function MatricSwitcher() {
  const matricGroup = useIdentityStore((s) => s.matricGroup);
  const setMatricGroup = useIdentityStore((s) => s.setMatricGroup);

  return (
    <select
      className="rounded-md border bg-white/70 px-2 py-1 text-sm"
      value={matricGroup ?? ""}
      onChange={(e) => setMatricGroup(e.target.value ? (e.target.value as MatricGroup) : null)}
      aria-label="選擇學制"
    >
      <option value="">全部學制</option>
      {SELECTOR_GROUPS.map((g) => (
        <option key={g} value={g}>{GROUP_LABEL[g]}</option>
      ))}
    </select>
  );
}
