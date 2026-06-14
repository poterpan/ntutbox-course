import { describe, it, expect, beforeEach } from "vitest";
import { useDraftStore } from "./draft-store";

describe("draft-store", () => {
  beforeEach(() => useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] }));

  it("place assigns next priority and dedups", () => {
    const s = useDraftStore.getState();
    s.place("A"); s.place("B"); s.place("A"); // A twice
    const p = useDraftStore.getState().placed;
    expect(p.map((x) => x.offering_id)).toEqual(["A", "B"]);
    expect(p.find((x) => x.offering_id === "A")!.priority).toBe(1);
    expect(p.find((x) => x.offering_id === "B")!.priority).toBe(2);
  });

  it("favorite toggles independently of placed and dedups", () => {
    const s = useDraftStore.getState();
    s.toggleFavorite("A"); s.toggleFavorite("A"); s.toggleFavorite("B");
    expect(useDraftStore.getState().favorites).toEqual(["B"]);
  });

  it("reorder within a group swaps priorities", () => {
    const s = useDraftStore.getState();
    s.place("A"); s.place("B"); // A=1, B=2
    s.setPriority("B", 1); s.setPriority("A", 2);
    const byId = (id: string) => useDraftStore.getState().placed.find((p) => p.offering_id === id)!;
    expect(byId("B").priority).toBe(1);
    expect(byId("A").priority).toBe(2);
  });

  it("reconcile drops placed/favorites whose offering_id no longer exists; returns dropped ids", () => {
    const s = useDraftStore.getState();
    s.place("A"); s.place("GONE"); s.toggleFavorite("ALSO_GONE");
    const dropped = s.reconcile(new Set(["A"]));
    expect(dropped.sort()).toEqual(["ALSO_GONE", "GONE"]);
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["A"]);
    expect(useDraftStore.getState().favorites).toEqual([]);
  });
});
