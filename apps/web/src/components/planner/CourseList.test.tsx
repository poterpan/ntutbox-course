import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CourseList } from "./CourseList";
import type { CourseOffering } from "@/lib/data/types";
import { useDraftStore } from "@/store/draft-store";

const courses = [
  { offering_id: "A", name: { zh: "微積分" }, credits: 3, teachers: [{ name: "王" }], meetings: [], classes: [] },
  { offering_id: "B", name: { zh: "線性代數" }, credits: 3, teachers: [{ name: "李" }], meetings: [], classes: [] },
] as unknown as CourseOffering[];

beforeEach(() => useDraftStore.setState({ termKey: "115-1", favorites: [], placed: [] }));

describe("CourseList", () => {
  it("renders items and ＋ places a course", async () => {
    render(<CourseList courses={courses} />);
    expect(screen.getByText("微積分")).toBeInTheDocument();
    await userEvent.click(screen.getAllByLabelText("排入")[0]);
    expect(useDraftStore.getState().placed.map((p) => p.offering_id)).toEqual(["A"]);
  });
  it("★ toggles favorite", async () => {
    render(<CourseList courses={courses} />);
    await userEvent.click(screen.getAllByLabelText("收藏")[1]);
    expect(useDraftStore.getState().favorites).toEqual(["B"]);
  });
});
