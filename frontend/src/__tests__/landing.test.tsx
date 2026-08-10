// The landing renders its own dark surface: every content section mounts in
// order, the booking form and footer are present, and the whole page is clean
// under axe (structure + ARIA — not contrast, which jsdom can't measure). The
// Platform product screens are code-split and gated on IntersectionObserver, so
// under the no-op test stub they stay as placeholders (no Recharts) — exactly the
// first-paint state we want to assert.

import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { PRELOAD_KEY } from "../landing/chrome/Preloader";
import { LandingPage } from "../landing/LandingPage";
import { axeCheck } from "./_axe";

// Skip the one-time counter preloader so the page mounts settled (the common
// returning-visitor state) and no rAF-driven state churn leaks past the test.
beforeEach(() => {
  window.sessionStorage.setItem(PRELOAD_KEY, "1");
});

// Hero (#top) → editorial + structured sections → booking CTA (#book), in order.
const SECTION_IDS = [
  "top",
  "approach",
  "industries",
  "platform",
  "configurable",
  "rules",
  "lifecycle",
  "growth",
  "security",
  "partner",
  "process",
  "faq",
  "book",
];

describe("LandingPage — render", () => {
  it("mounts every section in content order, plus the form and footer", () => {
    const { container } = render(<LandingPage />);

    for (const id of SECTION_IDS) {
      expect(container.querySelector(`#${id}`), `missing section #${id}`).not.toBeNull();
    }

    // a representative heading from across the page
    expect(screen.getByText("Differently.")).toBeInTheDocument();
    expect(screen.getByText("Every company is different.")).toBeInTheDocument();
    expect(screen.getByText("Designed around how you work.")).toBeInTheDocument();
    expect(screen.getByText("Nothing is generic.")).toBeInTheDocument();
    expect(screen.getByText("From opportunity to completion.")).toBeInTheDocument();
    expect(screen.getByText("Questions we usually hear.")).toBeInTheDocument();

    // the one functional feature + the footer bookend
    expect(
      screen.getByRole("button", { name: /book my discovery session/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/all rights reserved/i)).toBeInTheDocument();
  });

  it("keeps the product screens off first paint (placeholders, no charts)", () => {
    const { container } = render(<LandingPage />);
    expect(container.querySelector("#platform")).not.toBeNull();
    // no framed product screen and no Recharts mounted while out of view
    expect(container.querySelector('#platform figure[role="img"]')).toBeNull();
    expect(container.querySelector("#platform .recharts-wrapper")).toBeNull();
  });
});

describe("LandingPage — a11y", () => {
  it("has no axe violations (structure + ARIA)", async () => {
    expect(await axeCheck(<LandingPage />)).toHaveNoViolations();
  }, 20000);
});
