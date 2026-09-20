import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CourseDetailContent } from "./CourseDetailContent";
import { useTermStore } from "@/store/term-store";
import { useUiStore } from "@/store/ui-store";

// 只驗證「所屬微學程 chips」這層 enrichment；microprogram 目錄以 mock 注入，
// 不打真 fetch。buildProgramIndex 走真實實作（offering→programs 反查）。
const { mockUseMprograms } = vi.hoisted(() => ({ mockUseMprograms: vi.fn() }));
vi.mock("@/lib/planner/use-mprograms", () => ({ useMprograms: mockUseMprograms }));

const dirWith = { schema_version: 2, term_key: "115-1", programs: [
  { code: "AV2", name: "面板微學程", offering_ids: ["A"], courses: [], rules_text: null },
] } as never;
const dirNone = { schema_version: 2, term_key: "115-1", programs: [
  { code: "AV3", name: "創業家精神微學程", offering_ids: ["Z"], courses: [], rules_text: null },
] } as never;

function seedTerm() {
  useTermStore.setState({ status: "ready", termKey: "115-1", error: null, generation: 1,
    bundle: { termKey: "115-1", catalog: { courses: [
      { offering_id: "A", course_code: "2B05003", name: { zh: "資料結構", en: "Data Structures" }, credits: 3,
        teachers: [{ name: "王老師" }], meetings: [{ day: 1, periods: ["3", "4"] }], classes: [{ code: "2652", name: "資工五", kind: "regular" }],
        unit_name: "資工", language: "中文", notes_raw: "限資工系" },
    ] } as never, periods: { periods: [] } as never, classes: { classes: [] } as never, enrollment: null } as never });
}

beforeEach(() => {
  seedTerm();
  useUiStore.setState({ libraryTab: "courses", selectedProgramCode: null, detailOfferingId: "A", libraryOpen: false });
  mockUseMprograms.mockReset();
  mockGetDataSource.mockReturnValue(DEFAULT_SOURCE);
});

describe("CourseDetailContent — 所屬微學程 chips", () => {
  it("renders a chip for each owning micro-program and jumps on click", () => {
    mockUseMprograms.mockReturnValue({ data: dirWith, error: false, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" />);

    const chip = screen.getByRole("button", { name: /面板微學程/ });
    expect(chip).toBeInTheDocument();

    fireEvent.click(chip);
    const s = useUiStore.getState();
    expect(s.libraryTab).toBe("programs");
    expect(s.selectedProgramCode).toBe("AV2");
    expect(s.detailOfferingId).toBeNull();
  });

  it("renders nothing when the course belongs to no micro-program", () => {
    mockUseMprograms.mockReturnValue({ data: dirNone, error: false, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" />);
    expect(screen.queryByRole("button", { name: /微學程/ })).not.toBeInTheDocument();
    expect(screen.queryByText("所屬微學程")).not.toBeInTheDocument();
  });

  it("hides the block when showProgramChips=false, even with owning programs (shared-modal 就地詳情)", () => {
    mockUseMprograms.mockReturnValue({ data: dirWith, error: false, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" showProgramChips={false} />);
    expect(screen.queryByRole("button", { name: /面板微學程/ })).not.toBeInTheDocument();
    expect(screen.queryByText("所屬微學程")).not.toBeInTheDocument();
  });

  it("stays silent when the directory failed / is not yet loaded", () => {
    mockUseMprograms.mockReturnValue({ data: null, error: true, loading: false, retry: vi.fn() });
    render(<CourseDetailContent offeringId="A" />);
    expect(screen.queryByText("所屬微學程")).not.toBeInTheDocument();
  });
});


// ── 彈性學習（17-18 週）──────────────────────────────────────
// 用 getDataSource mock 注入 detail；元件是透過它取 syllabi 的。
const { mockGetDataSource } = vi.hoisted(() => ({ mockGetDataSource: vi.fn() }));
// 預設實作：既有測試不呼叫 seedDetail，也要能正常 render（不注入 detail）。
const DEFAULT_SOURCE = {
  getManifest: () => Promise.resolve({ terms: { "115-1": {} } }),
  getCourseDetail: () => Promise.resolve(null),
};
vi.mock("@/lib/data", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  getDataSource: mockGetDataSource,
}));

function seedDetail(syllabi: unknown[]) {
  // 元件樹也會用 getManifest（use-latest-term），mock 要一併提供，否則整個 render 掛掉。
  mockGetDataSource.mockReturnValue({
    getManifest: () => Promise.resolve({ terms: { "115-1": {} } }),
    getCourseDetail: () => Promise.resolve({
      term_key: "115-1", offering_id: "A", name: { zh: "資料結構" }, syllabi,
    }),
  });
}

describe("彈性學習（17-18 週）", () => {
  it("still renders the legacy dict shape (schema v2 data)", async () => {
    // 舊形狀不會因為遷移跑完就消失：資料管線回滾、尚未遷移的學期、以及 CDN／瀏覽器
    // 既有快取都會讓 dict 再冒出來。這是**永久**保險而不是過渡期測試，不要刪。
    mockUseMprograms.mockReturnValue({ data: dirNone, error: false, loading: false, retry: vi.fn() });
    // 用「基本資料表沒有的」欄位名，避免與課程資訊的「時數」撞名
    seedDetail([{ teacher_name: "王", schedule: "第一週…",
      flex_learning: { "類別": "線上數位教材學習", "彈性時數": "4", "未來新欄位": "某值" } }]);
    render(<CourseDetailContent offeringId="A" />);
    expect(await screen.findByText("彈性學習（17-18 週）")).toBeInTheDocument();
    for (const t of ["類別", "線上數位教材學習", "彈性時數", "未來新欄位", "某值"]) {
      expect(await screen.findByText(t)).toBeInTheDocument();
    }
  });

  it("renders the label/value array in source order (schema v3 shape)", async () => {
    // 順序是契約：消費端照陣列順序渲染，不必知道欄位名。
    mockUseMprograms.mockReturnValue({ data: dirNone, error: false, loading: false, retry: vi.fn() });
    seedDetail([{ teacher_name: "王", schedule: "第一週…", flex_learning: [
      { label: "類別", value: "線上數位教材學習" },
      { label: "彈性時數", value: "4" },
      { label: "未來新欄位", value: "某值" },
    ] }]);
    render(<CourseDetailContent offeringId="A" />);
    const title = await screen.findByText("彈性學習（17-18 週）");
    for (const t of ["類別", "線上數位教材學習", "彈性時數", "未來新欄位", "某值"]) {
      expect(await screen.findByText(t)).toBeInTheDocument();
    }
    const text = title.parentElement?.textContent ?? "";
    expect(text.indexOf("類別")).toBeLessThan(text.indexOf("彈性時數"));
    expect(text.indexOf("彈性時數")).toBeLessThan(text.indexOf("未來新欄位"));
  });

  it("keeps duplicate labels instead of collapsing them", async () => {
    // dict 形狀下後者會覆蓋前者、靜默掉一列；陣列必須兩列都渲染。
    mockUseMprograms.mockReturnValue({ data: dirNone, error: false, loading: false, retry: vi.fn() });
    seedDetail([{ teacher_name: "王", schedule: "第一週…", flex_learning: [
      { label: "內容", value: "第17週：課程口試" },
      { label: "內容", value: "第18週：反思報告" },
    ] }]);
    render(<CourseDetailContent offeringId="A" />);
    expect(await screen.findByText("第17週：課程口試")).toBeInTheDocument();
    expect(screen.getByText("第18週：反思報告")).toBeInTheDocument();
    expect(screen.getAllByText("內容")).toHaveLength(2);
  });

  it("is omitted when the course has no flex learning", async () => {
    mockUseMprograms.mockReturnValue({ data: dirNone, error: false, loading: false, retry: vi.fn() });
    seedDetail([{ teacher_name: "王", schedule: "第一週…" }]);
    render(<CourseDetailContent offeringId="A" />);
    expect(await screen.findByText("課程進度")).toBeInTheDocument();
    expect(screen.queryByText("彈性學習（17-18 週）")).toBeNull();
  });
});
