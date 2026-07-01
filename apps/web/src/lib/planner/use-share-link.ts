"use client";
import { useEffect, useRef } from "react";
import { parseCourseLink } from "@/lib/share/course-link";
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
  const status = useTermStore((s) => s.status);
  const loadedTermKey = useTermStore((s) => s.termKey);
  const { byId } = useTermCourses();
  const showToast = useToast((s) => s.show);

  const pendingRef = useRef<{ termKey: string; offeringId: string } | null>(null);
  const handledRef = useRef(false);

  // 進站解析一次：記下目標、切學期、清 URL 參數。
  useEffect(() => {
    if (typeof window === "undefined") return;
    const parsed = parseCourseLink(window.location.search);
    if (!parsed) return;
    pendingRef.current = parsed;
    setSelectedTerm(parsed.termKey);

    const url = new URL(window.location.href);
    url.searchParams.delete("term");
    url.searchParams.delete("course");
    window.history.replaceState({}, "", url.pathname + url.search + url.hash);
  }, [setSelectedTerm]);

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
