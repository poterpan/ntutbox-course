import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NoTimeTray } from "./NoTimeTray";
import { useTermStore } from "@/store/term-store";
import { useDraftStore } from "@/store/draft-store";

const courses = [
  { offering_id: "T", name: { zh: "微積分" }, credits: 3, teachers: [], meetings: [{ day: 1, periods: ["1"] }], classes: [] },
  { offering_id: "N", name: { zh: "實務專題" }, credits: 1, teachers: [], meetings: [], classes: [] }, // no time
];

beforeEach(() => {
  useTermStore.setState({
    status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never,
  });
});

describe("NoTimeTray", () => {
  it("renders nothing when no placed course lacks a time", () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "T", priority: 1 }] });
    const { container } = render(<NoTimeTray />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists placed no-time courses and 退選 removes them", async () => {
    useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [{ offering_id: "T", priority: 1 }, { offering_id: "N", priority: 2 }] });
    render(<NoTimeTray />);
    expect(screen.getByText("實務專題")).toBeInTheDocument();
    expect(screen.queryByText("微積分")).not.toBeInTheDocument(); // has a time → not in tray
    await userEvent.click(screen.getByLabelText("退選 實務專題"));
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["T"]);
  });
});
