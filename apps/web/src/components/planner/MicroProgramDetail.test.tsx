import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MicroProgramDetail } from "./MicroProgramDetail";
import type { CourseOffering, MicroProgram } from "@/lib/data/types";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";
import { OAA_MPROGRAM_URL } from "@/lib/planner/mprogram-links";

function seedTerm(courses: Partial<CourseOffering>[]) {
  useTermStore.setState({
    status: "ready",
    termKey: "115-1",
    error: null,
    generation: 1,
    bundle: {
      termKey: "115-1",
      catalog: { courses } as never,
      periods: { periods: [] } as never,
      classes: { classes: [] } as never,
      enrollment: null,
    } as never,
  } as never);
}

// program：進階＋基礎兩分類（進階先出現於陣列以測排序）；C_BASE 有班、C_NONE 無班、103 反查不到（orphan）。
const program = {
  code: "AV2",
  name: "面板顯示微學程",
  offering_ids: ["101", "102", "103"],
  courses: [
    { course_code: "C_ADV", name_zh: "進階面板設計", credits: 3, category: "進階", category_raw: null, emi: false },
    { course_code: "C_BASE", name_zh: "面板概論", credits: 3, category: "基礎", category_raw: null, emi: false },
    { course_code: "C_NONE", name_zh: "未開課主題", credits: 2, category: "基礎", category_raw: null, emi: false },
  ],
  rules_text: "須修滿 9 學分。\n含基礎與進階各一門。",
} as unknown as MicroProgram;

const seededCourses: Partial<CourseOffering>[] = [
  { offering_id: "101", course_code: "C_BASE", name: { zh: "面板概論" }, credits: 3, classes: [{ code: "K1", name: "電子四甲" }] as never },
  { offering_id: "102", course_code: "C_ADV", name: { zh: "進階面板設計" }, credits: 3, classes: [{ code: "K2", name: "資工三甲" }] as never },
];

beforeEach(() => {
  useUiStore.setState({ selectedProgramCode: "AV2", detailOfferingId: null });
  seedTerm(seededCourses);
});

describe("MicroProgramDetail", () => {
  it("分類依固定順序分組（基礎 → 進階），課名與學分呈現", () => {
    render(<MicroProgramDetail program={program} />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["基礎", "進階"]);
    expect(screen.getByText("面板概論")).toBeInTheDocument();
    expect(screen.getAllByText("3 學分").length).toBeGreaterThan(0);
    expect(screen.getByText("2 學分")).toBeInTheDocument();
  });

  it("course_code 重複（課程標準同編碼多列）→ 去重只呈現一列", () => {
    // 面板/感測等學程實資料出現同 course_code 重複列，會撞 React key 並顯示重複；驗證去重。
    const dup = {
      ...program,
      courses: [
        { course_code: "C_BASE", name_zh: "面板概論", credits: 3, category: "基礎", category_raw: null, emi: false },
        { course_code: "C_BASE", name_zh: "面板概論", credits: 3, category: "基礎", category_raw: null, emi: false },
      ],
    } as unknown as MicroProgram;
    render(<MicroProgramDetail program={dup} />);
    expect(screen.getAllByText("面板概論")).toHaveLength(1);
  });

  it("context copy 逐字呈現", () => {
    render(<MicroProgramDetail program={program} />);
    expect(
      screen.getByText(
        "112 學年度起入學之日間部大學部，畢業前須完成跨領域學習（微學程為五種路徑之一）；修讀須於教務處公告期間登記。",
      ),
    ).toBeInTheDocument();
  });

  it("有班課顯示班級 chip、無班課顯示「本學期未開」", () => {
    render(<MicroProgramDetail program={program} />);
    expect(screen.getByRole("button", { name: "電子四甲" })).toBeInTheDocument();
    expect(screen.getByText("本學期未開")).toBeInTheDocument();
  });

  it("點班級 chip → openDetail 設 detailOfferingId", () => {
    render(<MicroProgramDetail program={program} />);
    fireEvent.click(screen.getByRole("button", { name: "電子四甲" }));
    expect(useUiStore.getState().detailOfferingId).toBe("101");
  });

  it("反查不到的 offering_id 以純文字列出（防呆），不成為可點 chip", () => {
    render(<MicroProgramDetail program={program} />);
    expect(screen.getByText(/103/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "103" })).toBeNull();
  });

  it("rules_text 以段落呈現（保留換行），並附 OAA 外連", () => {
    render(<MicroProgramDetail program={program} />);
    expect(screen.getByText(/須修滿 9 學分/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /教務處/ })).toHaveAttribute("href", OAA_MPROGRAM_URL);
  });

  it("rules_text 為 null → 顯示暫缺文案", () => {
    render(<MicroProgramDetail program={{ ...program, rules_text: null } as unknown as MicroProgram} />);
    expect(screen.getByText("規定原文暫缺，請以教務處專區為準")).toBeInTheDocument();
  });

  it("返回鈕清 selectedProgramCode", () => {
    render(<MicroProgramDetail program={program} />);
    fireEvent.click(screen.getByRole("button", { name: "返回微學程列表" }));
    expect(useUiStore.getState().selectedProgramCode).toBeNull();
  });

  it("courses 為空 → 課程標準暫缺，offering_ids 直接以可點 chip 列出", () => {
    seedTerm([{ offering_id: "201", course_code: "X", name: { zh: "某課" }, credits: 3, classes: [{ code: "K9", name: "機械二甲" }] as never }]);
    const empty = { ...program, courses: [], offering_ids: ["201"] } as unknown as MicroProgram;
    render(<MicroProgramDetail program={empty} />);
    expect(screen.getByText("課程標準暫缺，僅列本學期開課")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "機械二甲" }));
    expect(useUiStore.getState().detailOfferingId).toBe("201");
  });
});
