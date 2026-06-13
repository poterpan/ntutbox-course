import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { GlassPanel } from "./GlassPanel";
import { GlassCard } from "./GlassCard";
import { GlassBar } from "./GlassBar";

describe("glass primitives", () => {
  it("GlassPanel renders children with glass-surface", () => {
    render(<GlassPanel data-testid="p">hi</GlassPanel>);
    const el = screen.getByTestId("p");
    expect(el).toHaveTextContent("hi");
    expect(el.className).toContain("glass-surface");
  });
  it("GlassCard and GlassBar carry glass-surface and merge className", () => {
    render(<><GlassCard data-testid="c" className="custom-c">c</GlassCard><GlassBar data-testid="b">b</GlassBar></>);
    expect(screen.getByTestId("c").className).toContain("glass-surface");
    expect(screen.getByTestId("c").className).toContain("custom-c");
    expect(screen.getByTestId("b").className).toContain("glass-surface");
  });
});
