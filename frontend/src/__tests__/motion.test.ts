// Phase 6 acceptance (UI_REFACTOR.md): "no animation exceeds --dur-page", and
// "disabling motion leaves every flow fully usable".
//
// These are enforced rather than eyeballed: the duration tokens are parsed out
// of tokens.css, every CSS module is scanned for animations that outrun the
// budget, and the reduced-motion kill switch is asserted to still exist.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DUR } from "../shared/motion/durations";
import { useReducedMotion } from "../shared/motion/useReducedMotion";
import {
  contentTransition,
  overlayTransition,
  routeVariants,
} from "../shared/motion/variants";

const SRC = join(__dirname, "..");
const TOKENS = readFileSync(join(SRC, "shared/design/tokens.css"), "utf8");

function cssFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    if (entry === "node_modules") return [];
    if (statSync(path).isDirectory()) return cssFiles(path);
    return path.endsWith(".css") ? [path] : [];
  });
}

/** `--dur-fast: 140ms` -> ["fast", 140] */
function tokenDurations(): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [, name, ms] of TOKENS.matchAll(/--dur-([a-z]+):\s*(\d+)ms/g)) {
    out[name] = Number(ms);
  }
  return out;
}

describe("motion budget", () => {
  const tokens = tokenDurations();

  it("parses every duration token from tokens.css", () => {
    expect(Object.keys(tokens).sort()).toEqual(
      ["base", "fast", "instant", "page", "slow"],
    );
  });

  // durations.ts drives JS-side motion (Framer, Recharts) that cannot read a
  // custom property; if the two drift, one of them is lying.
  it("keeps durations.ts in step with tokens.css", () => {
    expect(DUR.instant).toBe(tokens.instant);
    expect(DUR.fast).toBe(tokens.fast);
    expect(DUR.base).toBe(tokens.base);
    expect(DUR.slow).toBe(tokens.slow);
    expect(DUR.page).toBe(tokens.page);
  });

  it("treats --dur-page as the ceiling", () => {
    for (const [name, ms] of Object.entries(tokens)) {
      expect(ms, `--dur-${name}`).toBeLessThanOrEqual(tokens.page);
    }
  });

  // The budget governs *one-shot* motion — entrances, exits, transitions.
  // An indefinite progress indicator is a different thing: its period is a
  // legibility choice (a spinner completing a turn in 480ms reads as frantic),
  // it communicates "still working" rather than moving something from A to B,
  // and the reduced-motion kill switch stops it anyway.
  it("has no one-shot CSS animation or transition longer than --dur-page", () => {
    const offenders: string[] = [];
    for (const file of cssFiles(SRC)) {
      const css = readFileSync(file, "utf8");
      for (const [match, value, unit] of css.matchAll(
        /(?:animation|transition)(?:-duration)?:[^;]*?(\d*\.?\d+)(ms|s)\b[^;]*;/g,
      )) {
        if (/\binfinite\b/.test(match)) continue; // covered by the next test
        const ms = unit === "s" ? Number(value) * 1000 : Number(value);
        if (ms > tokens.page) {
          offenders.push(`${file.replace(SRC, "src")}: ${match.trim()}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  // Looping motion is allowlisted by name, so a decorative loop cannot be added
  // without someone justifying it here. Phase 6 removed the rail's gatePulse
  // from this list: the live gate now wears a static ring and animates only on
  // arrival.
  it("only loops for known progress indicators", () => {
    const allowed = new Set(["spin", "shimmer"]);
    const found = new Set<string>();
    for (const file of cssFiles(SRC)) {
      for (const [, name] of readFileSync(file, "utf8").matchAll(
        /animation:\s*([\w-]+)[^;]*\binfinite\b/g,
      )) {
        found.add(name);
      }
    }
    expect([...found].filter((n) => !allowed.has(n))).toEqual([]);
  });

  it("keeps the reduced-motion kill switch in tokens.css", () => {
    expect(TOKENS).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    expect(TOKENS).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(TOKENS).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
    // an infinite loop that the kill switch does not stop would run forever
    expect(TOKENS).toMatch(/animation-iteration-count:\s*1\s*!important/);
  });
});

// The CSS kill switch above covers everything styled in CSS. Motion computed in
// JS — Framer's interpolation, Recharts' timer — has to opt out itself, so the
// pieces that decide are asserted directly.
describe("reduced motion (the JS path)", () => {
  afterEach(() => vi.unstubAllGlobals());

  function stubPrefersReduced(matches: boolean) {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }));
  }

  it("reports the user's preference", () => {
    stubPrefersReduced(true);
    expect(renderHook(() => useReducedMotion()).result.current).toBe(true);
    stubPrefersReduced(false);
    expect(renderHook(() => useReducedMotion()).result.current).toBe(false);
  });

  it("survives an environment with no matchMedia at all", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(() => renderHook(() => useReducedMotion())).not.toThrow();
    expect(renderHook(() => useReducedMotion()).result.current).toBe(false);
  });

  it("collapses every overlay transition to zero", () => {
    expect(overlayTransition(true).duration).toBe(0);
    expect(contentTransition(true).duration).toBe(0);
  });

  it("collapses the route transition to a plain swap", () => {
    const v = routeVariants(true) as Record<string, { transition?: { duration: number } }>;
    expect(v.animate.transition?.duration).toBe(0);
    expect(v.exit.transition?.duration).toBe(0);
    // no displacement either — a rise is still motion
    expect(v.initial).not.toHaveProperty("y");
  });

  it("keeps normal motion inside the page budget", () => {
    expect(overlayTransition(false).duration * 1000).toBeLessThanOrEqual(DUR.page);
    expect(contentTransition(false).duration * 1000).toBeLessThanOrEqual(DUR.page);
    const v = routeVariants(false) as Record<string, { transition?: { duration: number } }>;
    const total = (v.animate.transition!.duration + v.exit.transition!.duration) * 1000;
    expect(total).toBeLessThanOrEqual(DUR.page);
  });
});
