// The sidebar brand mark renders the company logo (no fill behind it) when
// present, and a monogram otherwise. It is display-only — the logo is uploaded
// from Settings → Company profile.

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { Sidebar } from "../shared/shell/Sidebar";

type Brand = Parameters<typeof Sidebar>[0]["brand"];

function renderSidebar(brand: Brand) {
  return render(
    <MemoryRouter>
      <Sidebar brand={brand} nav={[]} collapsed={false} onToggleCollapse={() => {}} />
    </MemoryRouter>,
  );
}

describe("Sidebar brand logo", () => {
  it("renders the company logo with no fill behind it", () => {
    renderSidebar({ title: "Acme", logo: "data:image/png;base64,AAAA" });
    const img = document.querySelector("img");
    expect(img?.getAttribute("src")).toBe("data:image/png;base64,AAAA");
    // the monogram chip's fill is removed for a real logo
    expect((img?.parentElement as HTMLElement).style.background).toBe("transparent");
  });

  it("falls back to a monogram without a logo", () => {
    renderSidebar({ title: "Acme Corp" });
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("AC")).toBeInTheDocument();
  });
});
