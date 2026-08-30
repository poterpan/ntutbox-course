import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AboutDialog } from "./AboutDialog";

/** 這些揭露是 E-E-A-T 的信任基礎（資料來源／非官方／開發者／回饋管道），
 * 稽核發現原本全站 0 命中。斷言在此，避免日後改版被誤刪。 */
describe("AboutDialog", () => {
  it("discloses data source, non-official status, developer and feedback channel", () => {
    render(<AboutDialog />);
    fireEvent.click(screen.getByRole("button", { name: "關於" }));

    // 資料來源＋更新頻率
    expect(screen.getByText(/官方課程查詢系統/)).toBeTruthy();
    expect(screen.getByText(/每日自動更新/)).toBeTruthy();
    // 非官方聲明
    expect(screen.getByText(/與國立臺北科技大學無隸屬或合作關係/)).toBeTruthy();
    // 開發者具名
    expect(screen.getByText(/PoterPan/)).toBeTruthy();
    // 來源連結指向校方系統，不是本站
    const src = screen.getByRole("link", { name: /官方課程查詢系統/ });
    expect(src.getAttribute("href")).toContain("aps.ntut.edu.tw");
  });
});
