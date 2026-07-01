"use client";
import { useEffect } from "react";
import { create } from "zustand";

// 極簡單則 toast：任何地方呼叫 useToast.getState().show("…")；<Toaster/> 掛一次。
interface ToastState {
  message: string | null;
  show: (message: string) => void;
  hide: () => void;
}

export const useToast = create<ToastState>((set) => ({
  message: null,
  show: (message) => set({ message }),
  hide: () => set({ message: null }),
}));

const AUTO_DISMISS_MS = 2600;

export function Toaster() {
  const message = useToast((s) => s.message);
  const hide = useToast((s) => s.hide);

  useEffect(() => {
    if (!message) return;
    const t = setTimeout(hide, AUTO_DISMISS_MS);
    return () => clearTimeout(t);
  }, [message, hide]);

  if (!message) return null;
  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4"
      role="status"
      aria-live="polite"
    >
      <div className="rounded-full bg-[var(--ink)] px-4 py-2 text-sm font-medium text-white shadow-lg">
        {message}
      </div>
    </div>
  );
}
