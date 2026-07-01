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
 * 不修改草稿（favorites/placed 不動）。開窗後清掉 URL 上的 share 參數，避免重整重觸發。
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

    const url = new URL(window.location.href);
    url.searchParams.delete("term");
    url.searchParams.delete("course");
    url.searchParams.delete("plan");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }, [setSelectedTerm, openSharedPlan]);

  // 目標學期就緒後開窗；找不到 → 提示。
  useEffect(() => {
    const pending = pendingRef.current;
    if (!pending || handledRef.current) return;

    if (status === "ready" && loadedTermKey === pending.termKey) {
      handledRef.current = true;
      pendingRef.current = null;
      if (byId(pending.offeringId)) openDetail(pending.offeringId);
      else showToast(NOT_FOUND);
    } else if (status === "error") {
      handledRef.current = true;
      pendingRef.current = null;
      showToast(NOT_FOUND);
    }
  }, [status, loadedTermKey, byId, openDetail, showToast]);
}
