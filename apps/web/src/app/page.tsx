"use client";
import { useEffect } from "react";
import { getDataSource } from "@/lib/data";
import { useTermStore } from "@/store/term-store";
import { GlassPanel } from "@/components/glass/GlassPanel";

const DEFAULT_TERM = "115-1";

export default function Page() {
  const { status, termKey, bundle, error, loadTerm, catalogCrawledAt, enrollmentObservedAt } = useTermStore();

  useEffect(() => {
    void loadTerm(DEFAULT_TERM, getDataSource());
  }, [loadTerm]);

  return (
    <main className="min-h-dvh p-6">
      <GlassPanel className="mx-auto max-w-xl p-6">
        <h1 className="text-lg font-semibold">北科盒子 排課（M1-A 煙霧測試）</h1>
        {status === "loading" && <p className="mt-3 text-sm text-zinc-500">載入中…</p>}
        {status === "error" && (
          <p className="mt-3 text-sm text-red-600">載入失敗：{error}</p>
        )}
        {status === "ready" && bundle && (
          <div className="mt-3 space-y-1 text-sm">
            <p>學期：{termKey}（{bundle.catalog.courses?.length ?? 0} 門課）</p>
            <p className="text-zinc-500">目錄更新：{catalogCrawledAt() ?? "—"}</p>
            <p className="text-zinc-500">人數更新：{enrollmentObservedAt() ?? "—"}</p>
          </div>
        )}
      </GlassPanel>
    </main>
  );
}
