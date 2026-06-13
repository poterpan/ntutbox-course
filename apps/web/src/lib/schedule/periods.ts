import type { PeriodTable } from "@/lib/data/types";

export function periodOrder(table: PeriodTable): Map<string, number> {
  return new Map((table.periods ?? []).map((p) => [p.token, p.order]));
}

export function sortPeriods(tokens: string[], table: PeriodTable): string[] {
  const ord = periodOrder(table);
  return [...tokens].sort((a, b) => (ord.get(a) ?? 99) - (ord.get(b) ?? 99));
}

export function periodLabel(token: string, table: PeriodTable): string {
  return (table.periods ?? []).find((p) => p.token === token)?.label ?? token;
}

/** Period tokens in display order (for grid rows). */
export function orderedPeriodTokens(table: PeriodTable): string[] {
  return [...(table.periods ?? [])].sort((a, b) => a.order - b.order).map((p) => p.token);
}
