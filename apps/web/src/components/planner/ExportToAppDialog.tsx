"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CopyIcon, QrCodeIcon, SmartphoneIcon } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccentButton } from "@/components/ui/accent-button";
import { useToast } from "@/components/ui/toast";
import { useDraftStore } from "@/store/draft-store";
import { useTermStore } from "@/store/term-store";
import { useTermCourses } from "@/lib/planner/use-term-courses";
import {
  buildPlanPayload,
  encodePlanPayload,
  buildPlanHandoffURL,
  QR_MAX_CHARS,
} from "@/lib/share/plan-payload";
import { shareOrCopy } from "@/lib/share/share-course";
import { trackEvent } from "@/lib/analytics";
import { countBucket } from "@/lib/analytics/events";
import { currentCampaignKey } from "@/lib/analytics/campaign";

/**
 * 「以觸控為主的裝置」判定。刻意不重用 share-course.ts 的 prefersNativeShare()——
 * 那個還要求 navigator.share 存在，而我們這裡只想知道「這是手機還是桌機」。
 * 改動 prefersNativeShare 會連帶改到既有分享行為，不值得。
 */
function isTouchPrimary(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia("(hover: none) and (pointer: coarse)").matches;
}

export function ExportToAppDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const placed = useDraftStore((s) => s.placed);
  const termKey = useTermStore((s) => s.termKey);
  const catalogCrawledAt = useTermStore((s) => s.catalogCrawledAt());
  const { byId } = useTermCourses();
  const showToast = useToast((s) => s.show);

  const [url, setUrl] = useState<string | null>(null);
  const [qrUsable, setQrUsable] = useState(false);
  const [touch, setTouch] = useState(false);
  const [failed, setFailed] = useState(false);

  const payload = useMemo(
    () =>
      termKey ? buildPlanPayload({ termKey, placed, byId, catalogCrawledAt }) : null,
    [termKey, placed, byId, catalogCrawledAt],
  );

  useEffect(() => {
    if (!open) return;
    // matchMedia 只在 client 有意義（SSR 一律回 false）；開窗當下讀一次即可，
    // 不是資料同步、沒有可訂閱的來源。React Compiler over-flags this.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setTouch(isTouchPrimary());
  }, [open]);

  useEffect(() => {
    if (!open || !payload) return;
    let cancelled = false;
    // Data-fetch effect: 開窗/payload 變動時先清掉上一輪的錯誤旗標與舊連結，再開始非同步
    // 編碼——不清 url/qrUsable 的話，使用者會在新連結編碼完成前的短暫窗口看到／複製到
    // 對應上一版課表的連結。只在 (open, payload, termKey) 變動時跑一次。React Compiler
    // over-flags this — see CourseDetailContent for the same pattern.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFailed(false);
    setUrl(null);
    setQrUsable(false);
    void (async () => {
      try {
        const { encoded, compressed } = await encodePlanPayload(payload);
        if (cancelled) return;
        setUrl(buildPlanHandoffURL({ encoded, compressed }));
        setQrUsable(compressed && encoded.length <= QR_MAX_CHARS);
      } catch {
        if (cancelled) return;
        setFailed(true);
        setUrl(null);
        trackEvent("export_to_app_error", {
          ...(termKey ? { term_key: termKey } : {}),
          error_code: "payload_build_failed",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, payload, termKey]);

  const handleCopy = useCallback(async () => {
    if (!url) return;
    const r = await shareOrCopy(url, "我的預排課表", "我的預排課表｜北科盒子");
    if (r === "copied") showToast("已複製匯入連結");
    else if (r === "failed") showToast("複製失敗，請手動複製網址");
  }, [url, showToast]);

  const firstChoiceCount = payload?.c.filter((c) => c.s === 1).length ?? 0;
  const backupCount = payload?.c.filter((c) => c.s === 2).length ?? 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>匯入到北科盒子</DialogTitle>
        </DialogHeader>

        <p className="text-[13px] leading-6 text-[var(--ink-soft)]">
          {termKey ? `${termKey} · ` : ""}
          共 {payload?.c.length ?? 0} 門（第一志願 {firstChoiceCount} 門
          {backupCount > 0 ? `、備選 ${backupCount} 門` : ""}）。
          匯入後會存成 App 裡的預排草稿，<b>不會覆蓋你現有的課表</b>。
        </p>

        {failed && (
          <p className="text-[13px] leading-6 text-red-600">
            連結產生失敗，請重新整理頁面再試一次。
          </p>
        )}

        {url && touch && (
          // 真連結、非 JS 導向：Safari 對 JS 觸發的導向不保證吃 Universal Link
          <a
            href={url}
            className="inline-flex items-center justify-center gap-1.5 rounded-full bg-[var(--accent)] px-5 py-3 text-[15px] font-semibold text-white"
            onClick={() => {
              const bucket = countBucket(placed.length);
              const campaignKey = currentCampaignKey();
              if (bucket) {
                trackEvent("export_to_app_click", {
                  ...(termKey ? { term_key: termKey } : {}),
                  handoff_method: "universal_link",
                  course_count_bucket: bucket,
                  ...(campaignKey ? { campaign_key: campaignKey } : {}),
                });
              }
            }}
          >
            <SmartphoneIcon className="size-4" aria-hidden />
            在 App 中開啟
          </a>
        )}

        {url && !touch && qrUsable && (
          <div className="flex flex-col items-center gap-2 rounded-xl bg-white p-4">
            <QRCodeSVG value={url} size={360} level="L" marginSize={2} />
            <p className="text-[13px] text-[var(--ink-soft)]">用手機相機掃這個 QR 直接匯入</p>
          </div>
        )}

        {url && !touch && !qrUsable && (
          <p className="text-[13px] leading-6 text-[var(--ink-soft)]">
            這份課表的連結較長，QR 會過於密集不好掃描。請改用「複製連結」傳到手機開啟。
          </p>
        )}

        <AccentButton tone="soft" size="lg" onClick={handleCopy} disabled={!url} className="gap-1.5">
          <CopyIcon className="size-4" aria-hidden />
          複製連結
        </AccentButton>

        <p className="text-[12px] leading-5 text-[var(--ink-faint)]">
          <QrCodeIcon className="mr-1 inline size-3" aria-hidden />
          課表內容放在網址的 fragment 裡，不會傳送到伺服器。
        </p>
      </DialogContent>
    </Dialog>
  );
}
