// Cross-category AND, intra-category OR (spec §3.2).
export interface FilterState {
  weekdays: number[];   // 1..7 (ISO: Mon=1)
  periods: string[];    // period tokens "1".."9","N","A".."D"
  colleges: string[];   // 學院 names (via college-map)
  units: string[];      // unit_code
  classes: string[];    // class code
  emiOnly: boolean;
}

export const EMPTY_FILTER: FilterState = {
  weekdays: [], periods: [], colleges: [], units: [], classes: [], emiOnly: false,
};
