// Cross-category AND, intra-category OR (spec §3.2).
export type EmiFilter = "all" | "emi" | "non_emi"; // 關閉 / 只看英文授課 / 排除英文授課

export interface FilterState {
  weekdays: number[];   // 1..7 (ISO: Mon=1)
  periods: string[];    // period tokens "1".."9","N","A".."D"
  colleges: string[];   // 學院 names (via college-map)
  units: string[];      // unit_code
  classes: string[];    // class code
  categories: string[]; // requirement.category: required/elective/general/program
  emi: EmiFilter;       // 英文授課三態（循環按鈕）
}

export const EMPTY_FILTER: FilterState = {
  weekdays: [], periods: [], colleges: [], units: [], classes: [], categories: [], emi: "all",
};
