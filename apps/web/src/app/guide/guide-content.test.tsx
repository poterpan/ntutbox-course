import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import GuideIndexPage, { metadata as indexMetadata } from "./page";
import TimetablePage, { metadata as timetableMetadata } from "./timetable/page";
import SelectionPhasesPage, { metadata as selectionMetadata } from "./selection-phases/page";
import GeneralEducationPage, { metadata as geMetadata } from "./general-education/page";
import MicroProgramsPage, { metadata as mprogramMetadata } from "./micro-programs/page";
import { GUIDE_PAGES } from "@/lib/guide/pages";

/**
 * 指南頁承接的是「資訊型搜尋意圖」，內容本身就是這幾頁存在的理由——
 * 稽核指出本站原本零說明性文字。這些斷言釘住**每頁必須答到的重點**與**必要的揭露**，
 * 避免日後改版把關鍵事實或免責聲明順手刪掉（比照 AboutDialog.test.tsx 的理由）。
 *
 * 這是本 repo 第一組 render `src/app/**` 的測試：這幾頁是純 server component
 * （沒有 async、沒有 next/headers），RTL 可直接 render。
 */

const PAGES = [
  { name: "hub", Page: GuideIndexPage, metadata: indexMetadata, canonical: "/guide/" },
  { name: "timetable", Page: TimetablePage, metadata: timetableMetadata, canonical: "/guide/timetable/" },
  {
    name: "selection-phases",
    Page: SelectionPhasesPage,
    metadata: selectionMetadata,
    canonical: "/guide/selection-phases/",
  },
  {
    name: "general-education",
    Page: GeneralEducationPage,
    metadata: geMetadata,
    canonical: "/guide/general-education/",
  },
  {
    name: "micro-programs",
    Page: MicroProgramsPage,
    metadata: mprogramMetadata,
    canonical: "/guide/micro-programs/",
  },
] as const;

describe("每一頁指南的共同要求", () => {
  it.each(PAGES)("$name：canonical 指向自己（root layout 釘在 / 會蓋掉子頁）", ({ metadata, canonical }) => {
    expect(metadata.alternates?.canonical).toBe(canonical);
    expect(metadata.title).toBeTruthy();
    expect(metadata.description).toBeTruthy();
  });

  it.each(PAGES)("$name：有唯一的 h1", ({ Page }) => {
    render(<Page />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it.each(PAGES)("$name：帶資料來源、非官方聲明與「以學校公告為準」", ({ Page }) => {
    render(<Page />);
    // 用 getAllByText：這兩句同時出現在頁尾揭露與部分頁面的正文，getByText 會撞到多筆。
    expect(screen.getAllByText(/與國立臺北科技大學無隸屬或合作關係/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/一律以學校公告為準/).length).toBeGreaterThan(0);
    const source = screen.getByRole("link", { name: /官方課程查詢系統/ });
    expect(source.getAttribute("href")).toContain("aps.ntut.edu.tw");
    // 制度細節的權威導向教務處，不是本站。
    expect(screen.getByRole("link", { name: /教務處公告/ }).getAttribute("href")).toContain(
      "oaa.ntut.edu.tw",
    );
  });

  it.each(PAGES)("$name：有回排課器的站內 CTA", ({ Page }) => {
    render(<Page />);
    expect(screen.getByRole("link", { name: "到排課器查課" }).getAttribute("href")).toBe("/");
  });

  it.each(PAGES)("$name：JSON-LD 有 BreadcrumbList、且不含 FAQPage/QAPage", ({ Page }) => {
    const { container } = render(<Page />);
    const scripts = [...container.querySelectorAll('script[type="application/ld+json"]')];
    expect(scripts.length).toBeGreaterThan(0);
    const all = scripts.map((s) => s.innerHTML).join("");
    expect(all).toContain("BreadcrumbList");
    expect(all).not.toContain("FAQPage");
    expect(all).not.toContain("QAPage");
  });
});

describe("hub：/guide/", () => {
  it("列出全部四個主題並連到正確路徑", () => {
    render(<GuideIndexPage />);
    for (const page of GUIDE_PAGES) {
      const link = screen.getByRole("link", { name: new RegExp(page.heading.slice(0, 8)) });
      // next/link 在測試環境不會套 next.config 的 trailingSlash，所以結尾斜線是可選的；
      // 「站內連結一律帶結尾斜線」的契約由 lib/guide/pages.test.ts 的 guidePath() 釘住。
      expect(link.getAttribute("href")).toMatch(new RegExp(`^/guide/${page.slug}/?$`));
    }
  });

  it("明說哪些會逐年變動的東西不寫", () => {
    render(<GuideIndexPage />);
    expect(screen.getByText(/選課各階段的起訖日期/)).toBeTruthy();
    expect(screen.getByText(/學分上下限/)).toBeTruthy();
  });
});

describe("timetable：北科 課表／節次 查詢意圖", () => {
  it("節次模型講清楚不是 1..14，且列出 14 節的時間", () => {
    const { container } = render(<TimetablePage />);
    const text = container.textContent ?? "";
    expect(text).toContain("1、2、3、4、N、5、6、7、8、9、A、B、C、D");
    // 抽樣：第 1 節、中午 N、晚上 A、最後 D
    for (const hm of ["08:10", "09:00", "12:10", "13:00", "18:30", "19:20", "21:10", "22:00"]) {
      expect(text).toContain(hm);
    }
  });

  it("解釋課號與課程編碼的差別", () => {
    const { container } = render(<TimetablePage />);
    const text = container.textContent ?? "";
    expect(text).toContain("課號");
    expect(text).toContain("課程編碼");
    expect(text).toContain("每學期重新編");
  });

  it("列出六個修別符號", () => {
    const { container } = render(<TimetablePage />);
    const text = container.textContent ?? "";
    for (const symbol of ["○", "△", "☆", "●", "▲", "★"]) {
      expect(text).toContain(symbol);
    }
    expect(text).toContain("校訂共同必修");
    expect(text).toContain("專業選修");
  });

  it("誠實揭露來源沒有的欄位與衝堂判斷的精度上限", () => {
    const { container } = render(<TimetablePage />);
    const text = container.textContent ?? "";
    expect(text).toContain("單雙週");
    expect(text).toContain("人數上限");
    expect(text).toContain("班週會");
    expect(text).toContain("星期 × 節次");
  });
});

describe("selection-phases：北科大 選課 注意事項意圖", () => {
  it("四種機制都出現", () => {
    const { container } = render(<SelectionPhasesPage />);
    const text = container.textContent ?? "";
    for (const name of ["期末網路初選", "志願選填", "開學後加退選", "獨立登記"]) {
      expect(text).toContain(name);
    }
  });

  it("點出志願分發不是先搶先贏、跨系班要等加退選", () => {
    const { container } = render(<SelectionPhasesPage />);
    const text = container.textContent ?? "";
    expect(text).toContain("不是先搶先贏");
    expect(text).toContain("跨系");
  });

  it("常見錯誤訊息附意思與下一步，並標明是實測整理而非官方文件", () => {
    const { container } = render(<SelectionPhasesPage />);
    const text = container.textContent ?? "";
    expect(text).toContain("※不是本班課程※");
    expect(text).toContain("選課人數已達上限");
    expect(text).toContain("實測");
  });

  it("明說日期每年不同、這頁不寫", () => {
    render(<SelectionPhasesPage />);
    expect(screen.getByText(/各階段的開放與截止時間每學期公告都不一樣/)).toBeTruthy();
  });
});

describe("general-education：北科 通識 課程意圖", () => {
  it("列出博雅四向度", () => {
    const { container } = render(<GeneralEducationPage />);
    const text = container.textContent ?? "";
    for (const dim of ["人文與藝術", "社會與法治", "自然與科學", "創新與創業"]) {
      expect(text).toContain(dim);
    }
  });

  it("解釋課程池班級與佔位課（查課時最容易誤解的兩件事）", () => {
    const { container } = render(<GeneralEducationPage />);
    const text = container.textContent ?? "";
    expect(text).toContain("課程池");
    expect(text).toContain("博雅課程(一)");
    expect(text).toContain("體育專項");
    expect(text).toContain("佔位課");
  });

  it("不寫各向度應修學分（無法查證）", () => {
    render(<GeneralEducationPage />);
    expect(screen.getByText(/本站無法查證，所以不寫/)).toBeTruthy();
  });
});

describe("micro-programs：北科 微學程意圖", () => {
  it("點出登記修讀與選課是兩件事", () => {
    const { container } = render(<MicroProgramsPage />);
    const text = container.textContent ?? "";
    expect(text).toContain("登記修讀");
    expect(text).toContain("不經選課系統");
    expect(text).toContain("不會被認列");
  });

  it("列出課程分類與線上課程例外", () => {
    const { container } = render(<MicroProgramsPage />);
    const text = container.textContent ?? "";
    for (const cat of ["基礎", "核心", "總整", "進階", "應用"]) {
      expect(text).toContain(cat);
    }
    expect(text).toContain("ewant");
    expect(text).toContain("不在選課系統開班");
  });

  it("完整規章導向教務處微學程公告頁", () => {
    render(<MicroProgramsPage />);
    const link = screen.getByRole("link", { name: /微學程公告頁/ });
    expect(link.getAttribute("href")).toContain("oaa.ntut.edu.tw");
  });
});
