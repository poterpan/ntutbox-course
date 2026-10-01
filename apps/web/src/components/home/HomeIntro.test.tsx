import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { HomeIntro } from "./HomeIntro";
import type { HomeSummary } from "@/lib/home/home-summary";

// vitest 下 next/link 不讀 next.config 的 trailingSlash（會吐 "/browse"）；build 產物是 "/browse/"。比對前補斜線。
const href = (el: HTMLElement) => (el.getAttribute("href") ?? "").replace(/\/?$/, "/");

const SUMMARY: HomeSummary = {
  termKey: "115-1",
  courseCount: 2440,
  unitCount: 60,
  roomTermKey: "115-1",
  roomCount: 313,
  updatedAt: "2026-10-01 07:24",
  topUnits: [
    { slug: "59", unitName: "資工系", courseCount: 120 },
    { slug: "aa", unitName: "通識中心", courseCount: 90 },
  ],
};

describe("HomeIntro", () => {
  it("h2 標題（不是 h1：首頁 h1 是排課器的品牌標題）", () => {
    render(<HomeIntro summary={SUMMARY} />);
    expect(screen.getByRole("heading", { level: 2, name: "北科大排課・選課規劃" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("四個入口：課程總覽／教室課表／選課指南／北科盒子 App（外連）", () => {
    render(<HomeIntro summary={SUMMARY} />);
    expect(href(screen.getByRole("link", { name: /^課程總覽/ }))).toBe("/browse/");
    expect(href(screen.getByRole("link", { name: /^教室課表/ }))).toBe("/rooms/");
    expect(href(screen.getByRole("link", { name: /^選課指南/ }))).toBe("/guide/");
    const app = screen.getByRole("link", { name: /^北科盒子 App ↗/ });
    expect(app).toHaveAttribute("href", "https://ntutbox.com/");
    expect(app).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("本學期數據", () => {
    const { container } = render(<HomeIntro summary={SUMMARY} />);
    const dl = within(container.querySelector("dl")!);
    expect(dl.getByText("115-1")).toBeInTheDocument();
    expect(dl.getByText("2440 門")).toBeInTheDocument();
    expect(dl.getByText("60 個")).toBeInTheDocument();
    expect(dl.getByText("313 間")).toBeInTheDocument();
    expect(dl.getByText("2026-10-01 07:24")).toBeInTheDocument();
  });

  it("熱門系所 → /browse/<slug>/，另附全部單位連結", () => {
    render(<HomeIntro summary={SUMMARY} />);
    expect(href(screen.getByRole("link", { name: /資工系/ }))).toBe("/browse/59/");
    expect(href(screen.getByRole("link", { name: /通識中心/ }))).toBe("/browse/aa/");
    expect(href(screen.getByRole("link", { name: "全部 60 個開課單位 →" }))).toBe("/browse/");
  });

  it("教室學期與預設學期不同 → 標出教室學期；沒有教室／時間 → 不顯示那格", () => {
    const { rerender } = render(<HomeIntro summary={{ ...SUMMARY, termKey: "115-2", roomTermKey: "115-1" }} />);
    expect(screen.getByText("教室（115-1）")).toBeInTheDocument();
    rerender(<HomeIntro summary={{ ...SUMMARY, roomTermKey: null, roomCount: null, updatedAt: null }} />);
    expect(screen.queryByText(/^教室/, { selector: "dt" })).toBeNull();
    expect(screen.queryByText("資料更新")).toBeNull();
  });
});
