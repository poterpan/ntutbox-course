import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { MatricGroup } from "@/lib/planner/matric";

// 使用者身分：手動選的「學制」（不登入、不打學校系統，見身分模型決策）。
// 跨學期共用、persist 到 localStorage。未來北科盒子 App 可用 URL 參數帶入覆寫。
interface IdentityState {
  matricGroup: MatricGroup | null;  // null = 全部（未選身分）
  setMatricGroup: (g: MatricGroup | null) => void;
}

export const useIdentityStore = create<IdentityState>()(
  persist(
    (set) => ({
      matricGroup: null,
      setMatricGroup: (matricGroup) => set({ matricGroup }),
    }),
    { name: "ntutbox-identity", version: 1 },
  ),
);
