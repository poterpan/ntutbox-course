import { create } from "zustand";
import { analyticsAvailable } from "@/lib/analytics/config";
import { bootstrapConsentMode, updateConsentMode } from "@/lib/analytics";
import { captureCampaignKey } from "@/lib/analytics/campaign";
import {
  clearAnalyticsCookies,
  readConsent,
  writeConsent,
  type ConsentState,
} from "@/lib/analytics/consent";

/**
 * 成效分析同意狀態。cookie 是真相來源（跨 subdomain 與官網共用），這個 store 只是
 * 讓 banner 與 GA loader 共享同一份 React 狀態。
 *
 * `hydrated` 在掛載後才為 true：SSR/首繪一律不畫 banner，避免 hydration mismatch。
 */
interface ConsentStoreState {
  consent: ConsentState;
  hydrated: boolean;
  hydrate: () => void;
  grant: () => void;
  deny: () => void;
  revoke: () => void;
}

export const useConsentStore = create<ConsentStoreState>((set, get) => ({
  consent: "unknown",
  hydrated: false,

  hydrate: () => {
    if (get().hydrated) return;
    const consent = readConsent();
    set({ consent, hydrated: true });
    if (!analyticsAvailable()) return;
    // 純本地：建 dataLayer、把 Consent Mode 四項設成 denied。不載入任何 Google 資源。
    bootstrapConsentMode();
    captureCampaignKey(window.location.search);
    if (consent === "granted") updateConsentMode(true);
  },

  grant: () => {
    writeConsent("granted");
    updateConsentMode(true);
    set({ consent: "granted", hydrated: true });
  },

  deny: () => {
    writeConsent("denied");
    updateConsentMode(false);
    set({ consent: "denied", hydrated: true });
  },

  revoke: () => {
    updateConsentMode(false);
    // 先寫 denied 再清 cookie：clearAnalyticsCookies 會連 consent cookie 一起刪，
    // 順序顛倒會留下 denied cookie 被自己刪掉、下次進站又跳 banner。
    clearAnalyticsCookies();
    writeConsent("denied");
    set({ consent: "denied", hydrated: true });
  },
}));
