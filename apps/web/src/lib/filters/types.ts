// Cross-category AND, intra-category OR (spec §3.2).
export type EmiFilter = "all" | "emi" | "non_emi"; // 關閉 / 只看英文授課 / 排除英文授課
export type MprogramFilter = "all" | "only" | "exclude"; // 關閉 / 只看微學程 / 排除微學程

export interface FilterState {
  weekdays: number[];   // 1..7 (ISO: Mon=1)
  periods: string[];    // period tokens "1".."9","N","A".."D"
  colleges: string[];   // 學院 names (via college-map)
  units: string[];      // unit_code
  classes: string[];    // class code
  categories: string[]; // requirement.category: required/elective/general/program
  emi: EmiFilter;       // 英文授課三態（循環按鈕）
  mprogram: MprogramFilter; // 微學程三態（循環按鈕）— 判準見 getProgramOidSet
}

export const EMPTY_FILTER: FilterState = {
  weekdays: [], periods: [], colleges: [], units: [], classes: [], categories: [], emi: "all", mprogram: "all",
};
