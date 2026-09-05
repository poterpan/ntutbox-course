import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { useMprograms } from "./use-mprograms";

// use-mprograms 的 cache / inflight 是模組層狀態、跨測試共用 →
// 每個測試各用一個 termKey，避免互相污染。
afterEach(() => {
  vi.restoreAllMocks();
});

it("fetches once and caches per term", async () => {
  const payload = { schema_version: 2, term_key: "115-1", programs: [] };
  const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(payload)) as never);
  const { result } = renderHook(() => useMprograms("115-1"));
  await waitFor(() => expect(result.current.data).not.toBeNull());
  renderHook(() => useMprograms("115-1"));
  expect(spy).toHaveBeenCalledTimes(1);
});

it("dedups concurrent first loads of the same term", async () => {
  // cache 只在 response 回來後才有值，所以「首載時多個 hook 並存」不受 cache 保護——
  // 這正是實際頁面的情形（Pane/List/Library/Favorites/DetailContent 共 5 處）。
  // 靠 inflight map 共用同一個 promise，只發一次請求。
  const payload = { schema_version: 2, term_key: "114-1", programs: [] };
  const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(payload)) as never);
  const a = renderHook(() => useMprograms("114-1"));
  const b = renderHook(() => useMprograms("114-1"));
  await waitFor(() => expect(a.result.current.data).not.toBeNull());
  await waitFor(() => expect(b.result.current.data).not.toBeNull());
  expect(spy).toHaveBeenCalledTimes(1);
});

it("error state, then retry() refetches and recovers", async () => {
  const payload = { schema_version: 2, term_key: "113-1", programs: [] };
  const spy = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response("nf", { status: 404 }) as never)
    .mockResolvedValueOnce(new Response(JSON.stringify(payload)) as never);

  const { result } = renderHook(() => useMprograms("113-1"));
  await waitFor(() => expect(result.current.error).toBe(true));
  expect(result.current.data).toBeNull();

  // 失敗不寫 cache，所以 retry() 必須真的重打一次
  act(() => { result.current.retry(); });
  await waitFor(() => expect(result.current.data).not.toBeNull());
  expect(result.current.error).toBe(false);
  expect(spy).toHaveBeenCalledTimes(2);
});
