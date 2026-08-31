import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FactTable } from "./FactTable";
import { GuideList, GuideNote, GuideSection } from "./GuideSection";

describe("FactTable", () => {
  it("表頭是 th[scope=col]，第一欄當列標題語意上仍在 tbody", () => {
    render(
      <FactTable caption="測試表" head={["節次", "開始"]} rows={[["N", "12:10"]]} />,
    );
    const headers = screen.getAllByRole("columnheader");
    expect(headers.map((h) => h.textContent)).toEqual(["節次", "開始"]);
    expect(headers[0].getAttribute("scope")).toBe("col");
    expect(screen.getByText("12:10")).toBeTruthy();
  });

  it("寬表格在自己的容器內橫向捲動，頁面本體不會出現橫向捲軸", () => {
    const { container } = render(<FactTable head={["a"]} rows={[["b"]]} />);
    expect(container.firstElementChild?.className).toContain("overflow-x-auto");
  });
});

describe("GuideSection", () => {
  it("標題是 h2 並帶可錨定的 id", () => {
    render(
      <GuideSection id="periods" title="節次">
        <p>內容</p>
      </GuideSection>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "節次" })).toBeTruthy();
    expect(document.getElementById("periods")).toBeTruthy();
  });
});

describe("GuideNote", () => {
  it("caution 走 accent token（不用 raw Tailwind 色，才吃 dark mode）", () => {
    const { container } = render(<GuideNote tone="caution">小心</GuideNote>);
    const cls = container.firstElementChild?.className ?? "";
    expect(cls).toContain("var(--accent)");
    expect(cls).toContain("var(--accent-ink)");
  });
});

describe("GuideList", () => {
  it("渲染成 ul/li", () => {
    render(<GuideList items={["一", "二"]} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
