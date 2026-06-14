export const UNCLASSIFIED = "未分類";

// unit_code → 學院. Curated from DESIGN §1.3 unit table (北科 ~7 colleges).
// Codes seen: 01 教務處, 05 進修部, 10 體育室, 14 通識中心, 2B 智動科, 30 機械,
// 31 電機, 32 化工, 34 土木, 36 電子, 37 工管, 38 工設, 39 建築, 54 應英,
// 59 資工, 91 學程, AA 校院級, AB 資財, AC 互動設計 …
const MAP: Record<string, string> = {
  "30": "機電學院", "2B": "機電學院", "33": "機電學院",         // 機械/智動/車輛
  "31": "電資學院", "36": "電資學院", "59": "電資學院", "61": "電資學院", // 電機/電子/資工/光電
  "32": "工程學院", "34": "工程學院", "35": "工程學院",         // 化工/土木/分子
  "37": "管理學院", "AB": "管理學院", "40": "管理學院", "41": "管理學院", // 工管/資財/企管/資管
  "38": "設計學院", "39": "設計學院", "AC": "設計學院",         // 工設/建築/互動
  "54": "人文與社會科學學院", "14": "人文與社會科學學院", "10": "人文與社會科學學院", // 應英/通識/體育
};

export function collegeOf(unitCode: string | null | undefined): string {
  if (!unitCode) return UNCLASSIFIED;
  return MAP[unitCode] ?? UNCLASSIFIED;
}

export function allColleges(): string[] {
  return [...new Set(Object.values(MAP)), UNCLASSIFIED];
}
