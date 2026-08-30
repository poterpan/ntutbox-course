"use client";
import { useEffect } from "react";
import { AccentButton } from "@/components/ui/accent-button";
import { analyticsAvailable } from "@/lib/analytics/config";
import { useConsentStore } from "@/store/consent-store";

const PRIVACY_URL = "https://ntutbox.com/privacy/";

/**
 * 成效分析同意詢問（§4）。同意／拒絕**同等可見**（同尺寸、只差色調）、無預勾選、
 * 無誘導文案；沒選之前一律不載入任何 Google 資源。撤回入口在官網隱私頁（跨 subdomain
 * 共用同一個 cookie），這裡提供可到達的連結。
 */
export function AnalyticsConsent() {
  const consent = useConsentStore((s) => s.consent);
  const hydrated = useConsentStore((s) => s.hydrated);
  const grant = useConsentStore((s) => s.grant);
  const deny = useConsentStore((s) => s.deny);

  useEffect(() => {
    useConsentStore.getState().hydrate();
  }, []);

  // GA 本來就不會在這個環境跑（env 未設 / host 不允許）→ 不必問，也不該擋畫面。
  if (!hydrated || consent !== "unknown" || !analyticsAvailable()) return null;

  return (
    <div
      role="region"
      aria-label="成效分析同意"
      // z 序：Dialog(z-50)/Toast(z-100) 之下，其餘之上。
      // sm 以上 CreditSummary 收成單列（約 64px）→ bottom-20 剛好疊在它上方，不遮匯出/分享。
      // 窄機必須讓開「課程庫」FAB（fixed bottom-28 h-12 z-30）——那是行動版唯一的搜尋入口，
      // 被蓋住時首訪者在回答同意前無法查任何課，與本卡文案「拒絕也能正常使用全部功能」相悖。
      // bottom-44（176px）= FAB 底 112px + FAB 高 48px + 16px 間距。
      className="fixed inset-x-3 bottom-44 z-40 sm:inset-x-auto sm:right-4 sm:bottom-20 sm:w-[26rem]"
    >
      {/* 底色改用 glass token 的 strong 階：這張卡會壓在課程列（滿滿的「排入」按鈕）上方，
          用預設 0.78 透明度時文字會被背後內容干擾。 */}
      <div className="glass-surface rounded-2xl px-4 py-3.5" style={{ background: "var(--glass-bg-strong)" }}>
        <p className="text-sm font-bold text-[var(--ink)]">要幫我們看看排課好不好用嗎？</p>
        <p className="mt-1 text-xs leading-relaxed text-[var(--ink-soft)]">
          同意後我們會用 Google Analytics 記錄匿名的頁面瀏覽與功能使用（例如排了幾門課）。
          <b className="font-semibold text-[var(--ink)]">不會</b>
          傳送你的搜尋文字、課號、課表內容或任何身分資料。拒絕也能正常使用全部功能。
        </p>
        <div className="mt-3 flex items-center gap-2">
          <AccentButton tone="solid" size="lg" className="flex-1" onClick={grant}>
            同意
          </AccentButton>
          <AccentButton tone="soft" size="lg" className="flex-1" onClick={deny}>
            拒絕
          </AccentButton>
        </div>
        <a
          href={PRIVACY_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2.5 inline-block text-xs font-medium text-[var(--accent-ink)] underline decoration-[var(--accent-ink)]/30 underline-offset-2 hover:decoration-[var(--accent-ink)]"
        >
          隱私政策與分析設定
        </a>
      </div>
    </div>
  );
}
