"use client";
import { useEffect } from "react";
import Script from "next/script";
import { usePathname } from "next/navigation";
import { analyticsAvailable, measurementId } from "@/lib/analytics/config";
import { configureGa, trackPageView } from "@/lib/analytics";
import { useConsentStore } from "@/store/consent-store";

/**
 * gtag.js loader。**同意前不掛任何 <Script>**，所以未同意的訪客不會有一個 byte 打到
 * googletagmanager.com / google-analytics.com（§4 opt-in）。
 *
 * page_view 手動送（config 帶 send_page_view:false）：同意後補送當前頁，之後只在
 * pathname 真的變了才再送。use-share-link 用 replaceState 清 query 不會動 pathname，
 * 因此不會重複送。
 */
export function GoogleAnalytics() {
  const id = measurementId();
  const consent = useConsentStore((s) => s.consent);
  const hydrated = useConsentStore((s) => s.hydrated);
  const pathname = usePathname();

  useEffect(() => {
    useConsentStore.getState().hydrate();
  }, []);

  const ready = hydrated && consent === "granted" && analyticsAvailable();

  useEffect(() => {
    if (!ready) return;
    // config 先進 dataLayer 佇列、再 page_view；gtag.js 載入後照順序處理。
    configureGa();
    trackPageView();
  }, [ready, pathname]);

  if (!ready || !id) return null;
  return (
    <Script
      id="ga4-gtag"
      strategy="afterInteractive"
      src={`https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(id)}`}
    />
  );
}
