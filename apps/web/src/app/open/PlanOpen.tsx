"use client";

import { useEffect, useState } from "react";

/** App 端接收預排課表的正式網址。與 `buildPlanHandoffURL` 的預設 origin 一致。 */
const APP_HANDOFF_BASE = "https://ntutbox.com/plan/";

/**
 * QR 掃描的中繼頁。
 *
 * ## 為什麼需要這一頁
 *
 * iOS 內建的條碼掃描器掃到 `https://ntutbox.com/plan/#…` 時，會依 AASA 認出這是
 * 北科盒子的連結、**把 App 啟動起來，但不把 URL 交給 App**。實機驗證（2026-09-05）：
 *
 * | 來源 | App 啟動 | URL 送達 |
 * |---|---|---|
 * | iMessage 點連結（冷啟動） | ✓ | ✓ |
 * | 內建掃描器（冷啟動） | ✓ | **✗** |
 *
 * 用最單純的 `https://ntutbox.com/share/abcdefgh`（短、無 fragment）測也一樣，
 * 所以與連結長度、fragment、QR 密度都無關——是掃描器那條路徑不傳遞 URL。
 * App 端收不到的東西沒辦法處理，只能改傳遞方式。
 *
 * 因此 QR 改成指向這一頁：**這一頁不在 AASA 的授權路徑裡**，掃描器會把它當普通
 * 網頁在 Safari 開啟，再由使用者按一下按鈕跨網域跳到 `ntutbox.com/plan/`——
 * 跨網域的「使用者點擊」是會觸發 universal link 的。
 *
 * ## ⚠️ 絕對不要改成自動跳轉
 *
 * `location.href = …` / `location.replace(…)` 這類由 JS 發起的導航**不會**觸發
 * universal link（Apple 刻意排除，否則使用者永遠回不到網站）。這一頁的存在意義
 * 就是那一下**使用者親自點擊**，自動跳轉會讓整頁失去作用、退回原本的問題。
 *
 * ## 沒裝 App 的人
 *
 * 不需要另外處理：按鈕在沒有 App 時就是一般的網頁導航，會落到
 * `ntutbox.com/plan/` 的說明頁，那裡已經有課數摘要與 App Store 連結。
 * 同一顆按鈕同時服務兩種人，這一頁不必自己再做一份。
 */
export function PlanOpen() {
  const [target, setTarget] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // fragment 原樣轉走，不解析也不重組：這一頁不需要知道裡面是什麼，
    // 少一份解碼實作就少一個會與 App／官網落地頁漂移的地方。
    const hash = window.location.hash.replace(/^#/, "");
    setTarget(hash ? `${APP_HANDOFF_BASE}#${hash}` : null);
    setReady(true);
  }, []);

  return (
    <main className="flex min-h-dvh items-center justify-center p-6">
      <div className="glass-surface w-full max-w-md rounded-2xl p-8 text-center">
        <h1 className="text-lg font-semibold text-[var(--ink)]">預排課表</h1>

        {!ready ? (
          <p className="mt-2 text-sm text-[var(--ink-soft)]">讀取中…</p>
        ) : target ? (
          <>
            <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">
              按下面的按鈕就會在「北科盒子」App 裡開啟這份課表。
            </p>
            {/*
              必須是真的 <a>，而且必須由使用者親自點——理由見檔頭。
              也刻意不加 target="_blank"：新分頁會讓 universal link 的判定更不穩定。
            */}
            <a
              href={target}
              className="mt-6 inline-block w-full rounded-xl bg-[var(--accent)] px-5 py-3 text-sm font-semibold text-white"
            >
              在 App 中開啟
            </a>
            <p className="mt-4 text-[13px] leading-6 text-[var(--ink-faint)]">
              還沒安裝 App 的話，這個按鈕會帶你到說明頁。
            </p>
          </>
        ) : (
          <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">
            這個網址沒有帶課表資料。請回到排課系統重新產生一次 QR 或分享連結。
          </p>
        )}
      </div>
    </main>
  );
}
