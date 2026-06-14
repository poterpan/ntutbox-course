import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FavoritesList } from "./FavoritesList";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";

beforeEach(() => {
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses: [{ offering_id: "A", name: { zh: "微積分" }, credits: 3, teachers: [], meetings: [], classes: [] }] } as never,
      periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
  useDraftStore.setState({ termKey: "115-1", favorites: ["A"], placed: [] });
});

describe("FavoritesList", () => {
  it("shows favorited courses and can place from here", async () => {
    render(<FavoritesList />);
    expect(screen.getByText("微積分")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("排入"));
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["A"]);
  });
});
