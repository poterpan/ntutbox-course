"use client";
import { useEffect, useRef } from "react";
import { parseCourseLink } from "@/lib/share/course-link";
import { parsePlanLink } from "@/lib/share/plan-link";
import { useUiStore } from "@/store/ui-store";
import { useTermStore } from "@/store/term-store";
import { useTermCourses } from "./use-term-courses";
import { useToast } from "@/components/ui/toast";

const NOT_FOUND = "此課程連結的課程可能已更新或不存在";

/**
 * F-A 收件端：進站若帶 ?term & ?course，切到該學期、待資料就緒後開該課資訊窗。
 * 不修改草稿（favorites/placed 不動）。URL 參數保留（可分享、可被搜尋引擎區分）；
 * 重整＝重新開窗（deep link 語意）。document.title 由 useCourseTitle 負責。
 * 掛在 planner 根一次即可。
 */
export function useShareLink() {
  const setSelectedTerm = useUiStore((s) => s.setSelectedTerm);
  const openDetail = useUiStore((s) => s.openDetail);
  const openSharedPlan = useUiStore((s) => s.openSharedPlan);
  const status = useTermStore((s) => s.status);
  const loadedTermKey = useTermStore((s) => s.termKey);
  const { byId } = useTermCourses();
  const showToast = useToast((s) => s.show);

  const pendingRef = useRef<{ termKey: string; offeringId: string } | null>(null);
  const handledRef = useRef(false);

  // 進站解析一次：記下目標、切學期、清 URL 參數。?plan（整表，F-B）優先於 ?course（單堂，F-A）。
  useEffect(() => {
    if (typeof window === "undefined") return;
    const search = window.location.search;
    const plan = parsePlanLink(search);
    const course = plan ? null : parseCourseLink(search);
    if (!plan && !course) return;

    if (plan) {
      setSelectedTerm(plan.termKey);
      openSharedPlan({ termKey: plan.termKey, offeringIds: plan.offeringIds });
    } else if (course) {
      pendingRef.current = course;
      setSelectedTerm(course.termKey);
    }

    // 刻意「不」清掉 URL 上的 share 參數：
    // ① 使用者複製網址時要拿到真正指向該課的連結（清掉會複製成首頁）；
    // ② Googlebot 用渲染後的 DOM，清掉會讓 2,461 個課程 URL 的 location 全變成 "/"，
    //    在索引端無法區分（SEO 稽核實測：rendered location.href 全部塌成首頁）。
    //
    // 語意：URL 是 source of truth。handledRef 只擋「同一次 mount 內」重複開窗；
    // 重新整理會重新開該課的詳情窗——這是 deep link 應有的行為（等同重開分享連結），
    // 不是 bug。使用者要離開該課就關窗後自行導航，或直接編輯網址。
  }, [setSelectedTerm, openSharedPlan]);

  // 上/下一頁（popstate）→ 依網址重新對齊「開著哪一堂課」。
  //
  // 為什麼需要：課程詳情的「相關課程」連結（RelatedCourses）是真 anchor，點擊時攔下來
  // 就地換課 + `history.pushState`（不整頁重載、不清掉搜尋/篩選狀態）。沒有這段的話
  // 使用者按上一頁，網址會回到前一堂課但畫面停在後一堂——網址與 UI 說法不一致。
  // 只讀網址、只動 detailOfferingId：不碰草稿、不重載學期。
  useEffect(() => {
    if (typeof window === "undefined") return;
    const sync = () => {
      const course = parseCourseLink(window.location.search);
      openDetail(course ? course.offeringId : null);
    };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [openDetail]);

  // 目標學期就緒後開窗；找不到 → 提示。
  useEffect(() => {
    const pending = pendingRef.current;
    if (!pending || handledRef.current) return;

    if (status === "ready" && loadedTermKey === pending.termKey) {
      handledRef.current = true;
      pendingRef.current = null;
      // document.title 不在這裡管——由 useCourseTitle 跟著 detailOfferingId 走，
      // 才能在關窗/切課/切學期時正確還原（見 use-course-title.ts）。
      if (byId(pending.offeringId)) openDetail(pending.offeringId);
      else showToast(NOT_FOUND);
    } else if (status === "error") {
      handledRef.current = true;
      pendingRef.current = null;
      showToast(NOT_FOUND);
    }
  }, [status, loadedTermKey, byId, openDetail, showToast]);
}
