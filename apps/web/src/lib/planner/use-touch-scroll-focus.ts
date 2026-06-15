"use client";
import { useRef } from "react";

/**
 * Initial-focus helper for controlled (trigger-less) dialogs that contain a scrollable list.
 *
 * base-ui normally focuses the popup itself — not an inner input/button — when a dialog is
 * opened by touch. That avoids the iOS Safari quirk where auto-focusing a descendant leaves
 * the modal without a committed scroll target, so its inner list won't scroll until the user
 * taps a field or selects text. But that path only runs when `openMethod === 'touch'`, which
 * is set solely by `<Dialog.Trigger>`. Our planner dialogs are controlled (state-driven, no
 * trigger), so `openMethod` stays `null` and the first focusable always grabs focus.
 *
 * So we detect coarse pointers ourselves and focus the scroll container instead; mouse/keyboard
 * keep base-ui's default (first focusable — e.g. a search input — for immediate typing).
 *
 * Usage: spread the ref onto the scroll container (give it `tabIndex={-1}`) and pass
 * `initialFocus` to `<DialogContent>`.
 */
export function useTouchScrollFocus() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const initialFocus = (openType: string) => {
    const coarse =
      typeof window !== "undefined" && !!window.matchMedia?.("(pointer: coarse)").matches;
    return openType === "touch" || openType === "pen" || coarse ? scrollRef.current : true;
  };
  return { scrollRef, initialFocus };
}
