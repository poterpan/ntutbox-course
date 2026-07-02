import { describe, it, expect } from "vitest";
import { planCount, resolveShareOg } from "./og";

describe("planCount", () => {
  it("counts dot-separated ids, ignoring blanks", () => {
    expect(planCount("360744.361278.360753")).toBe(3);
    expect(planCount("")).toBe(0);
    expect(planCount("360744..")).toBe(1);
  });
});

describe("resolveShareOg", () => {
  const names = { "360744": "國文" };

  it("course → course-name title when found", () => {
    const og = resolveShareOg(new URLSearchParams("term=115-1&course=360744"), names);
    expect(og).toEqual({
      title: "國文｜北科盒子 排課",
      description: "在北科盒子 排課查看課程詳情、加入你的課表",
    });
  });

  it("course not in names → null (fallback to generic OG)", () => {
    expect(resolveShareOg(new URLSearchParams("term=115-1&course=999999"), names)).toBeNull();
  });

  it("course present but names null → null", () => {
    expect(resolveShareOg(new URLSearchParams("term=115-1&course=360744"), null)).toBeNull();
  });

  it("plan → count-based title", () => {
    const og = resolveShareOg(new URLSearchParams("term=115-1&plan=360744.361278"), null);
    expect(og).toEqual({
      title: "分享的課表 · 2 門課｜北科盒子 排課",
      description: "查看這份 2 門課的課表規劃",
    });
  });

  it("empty plan → null", () => {
    expect(resolveShareOg(new URLSearchParams("term=115-1&plan="), null)).toBeNull();
  });

  it("no share params → null", () => {
    expect(resolveShareOg(new URLSearchParams(""), null)).toBeNull();
  });
});
