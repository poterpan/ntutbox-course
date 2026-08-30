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
 * 不修改草稿（favorites/placed 不動）。URL 參數保留（可分享、可被搜尋引擎區分），
 * 重複觸發由 handledRef 擋。
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
    // 重整不會重複觸發，靠下方的 handledRef 擋（不是靠改網址）。
  }, [setSelectedTerm, openSharedPlan]);

  // 目標學期就緒後開窗；找不到 → 提示。
  useEffect(() => {
    const pending = pendingRef.current;
    if (!pending || handledRef.current) return;

    if (status === "ready" && loadedTermKey === pending.termKey) {
      handledRef.current = true;
      pendingRef.current = null;
      const course = byId(pending.offeringId);
      if (course) {
        openDetail(pending.offeringId);
        // hydration 會用 layout.tsx 的 metadata.title.default 蓋掉 edge worker 改寫的
        // <title>（worker/index.ts 的 HTMLRewriter）。Googlebot 讀的是渲染後的 DOM，
        // 不補這一步，2,461 個課程頁在索引端 title 全同。格式與 lib/share/og.ts 一致。
        const name = course.name?.zh;
        if (name) document.title = `${name}｜北科盒子 排課`;
      } else showToast(NOT_FOUND);
    } else if (status === "error") {
      handledRef.current = true;
      pendingRef.current = null;
      showToast(NOT_FOUND);
    }
  }, [status, loadedTermKey, byId, openDetail, showToast]);
}
