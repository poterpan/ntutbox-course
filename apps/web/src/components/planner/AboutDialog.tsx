"use client";
import { useState } from "react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

const NTUT_COURSE_SOURCE = "https://aps.ntut.edu.tw/course/tw/";
const APP_SITE = "https://ntutbox.com";
const REPO = "https://github.com/poterpan/ntutbox-course";

/**
 * 「關於」揭露：資料來源、更新方式、非官方聲明、開發者、回饋管道。
 *
 * 為什麼需要：SEO/E-E-A-T 稽核發現全站搜尋「資料來源」「非官方」「開發者」「聯絡」
 * 皆 0 命中——一個免登入呈現正式課務資料的工具沒有這些揭露，是明確的信任缺口。
 * 版面是 h-dvh app-shell 沒有頁尾可放，故收在對話框；文字同時進 layout 的 JSON-LD
 * （Organization.description / WebSite.publisher），讓爬蟲與 AI 不必執行 JS 也讀得到。
 */
export function AboutDialog() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg px-2.5 py-2 text-[11px] text-[var(--ink-faint)] transition-colors hover:bg-[var(--accent)]/10 hover:text-[var(--accent-ink)]"
      >
        關於
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[80vh] w-[92vw] max-w-lg overflow-auto p-6">
          <DialogTitle className="text-lg font-bold text-[var(--ink)]">關於北科盒子 排課</DialogTitle>
          <div className="mt-4 space-y-4 text-sm leading-relaxed text-[var(--ink-soft)]">
            <p>
              免登入的臺北科技大學（北科大）課程查詢與排課規劃工具：全文查課、多維篩選、
              衝堂偵測、學分統計、微學程瀏覽，排好後可匯入
              <a href={APP_SITE} target="_blank" rel="noopener noreferrer" className="text-[var(--accent-ink)] underline underline-offset-2"> 北科盒子 App </a>
              完成選課。
            </p>
            <section>
              <h3 className="font-semibold text-[var(--ink)]">資料來源</h3>
              <p className="mt-1">
                所有課程資料整理自北科大公開的
                <a href={NTUT_COURSE_SOURCE} target="_blank" rel="noopener noreferrer" className="text-[var(--accent-ink)] underline underline-offset-2">官方課程查詢系統</a>
                ，每日自動更新。本站僅供規劃參考，正式選課請以學校選課系統送出的結果為準；
                若與學校系統有出入，一律以學校公告為準。
              </p>
            </section>
            <section>
              <h3 className="font-semibold text-[var(--ink)]">非官方聲明</h3>
              <p className="mt-1">
                本站為學生獨立開發的非官方工具，與國立臺北科技大學無隸屬或合作關係，
                亦非校方委託建置。
              </p>
            </section>
            <section>
              <h3 className="font-semibold text-[var(--ink)]">開發與回饋</h3>
              <p className="mt-1">
                由北科學生 PoterPan 開發與維護。原始碼與問題回報：
                <a href={REPO} target="_blank" rel="noopener noreferrer" className="text-[var(--accent-ink)] underline underline-offset-2">GitHub</a>
                。
              </p>
            </section>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
