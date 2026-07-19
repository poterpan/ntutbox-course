import { renderHook, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { useMprograms } from "./use-mprograms";

it("fetches once and caches per term", async () => {
  const payload = { schema_version: 2, term_key: "115-1", programs: [] };
  const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(payload)) as never);
  const { result } = renderHook(() => useMprograms("115-1"));
  await waitFor(() => expect(result.current.data).not.toBeNull());
  renderHook(() => useMprograms("115-1"));
  expect(spy).toHaveBeenCalledTimes(1);
});

it("error state + retry", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nf", { status: 404 }) as never);
  const { result } = renderHook(() => useMprograms("999-9"));
  await waitFor(() => expect(result.current.error).toBe(true));
});
