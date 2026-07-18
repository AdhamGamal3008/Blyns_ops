// Automated WCAG AA contrast check over the design tokens.
//
// Reads tokens.css directly, resolves each custom property (following var()
// chains) to a hex value, and asserts the color pairings the UI actually uses.
// This is the Phase-1 "contrast rules pass an automated check" acceptance —
// fully custom, no dependency. If a token hex changes and drops a pairing below
// AA, this test fails and names the pair.

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// --- load & parse tokens.css ------------------------------------------------
// Read the real CSS file (Vitest stubs `import "*.css"` to empty, so we can't
// import it). Resolve from cwd whether tests run in frontend/ or the repo root.

function loadTokensCss(): string {
  const candidates = [
    "src/shared/design/tokens.css",
    "frontend/src/shared/design/tokens.css",
  ].map((p) => resolve(process.cwd(), p));
  const found = candidates.find((p) => existsSync(p));
  if (!found) throw new Error(`tokens.css not found (looked: ${candidates.join(", ")})`);
  return readFileSync(found, "utf8");
}

// strip comments so commented-out declarations (e.g. the Phase-8 dark block)
// are never parsed as live tokens
const rawCss = loadTokensCss().replace(/\/\*[\s\S]*?\*\//g, "");

const declarations = new Map<string, string>();
for (const match of rawCss.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
  declarations.set(match[1], match[2].trim());
}

const HEX = /^#[0-9a-fA-F]{6}$/;

/** Resolve a token name (with or without leading `--`) to an uppercase hex. */
function resolveHex(name: string, seen = new Set<string>()): string {
  const key = name.replace(/^--/, "");
  if (seen.has(key)) throw new Error(`cyclic token reference at --${key}`);
  seen.add(key);
  const value = declarations.get(key);
  if (!value) throw new Error(`unknown token --${key}`);
  if (HEX.test(value)) return value.toUpperCase();
  const ref = value.match(/^var\(\s*(--[\w-]+)\s*\)$/);
  if (ref) return resolveHex(ref[1], seen);
  throw new Error(`--${key} is not a color (got "${value}")`);
}

// --- WCAG math --------------------------------------------------------------

function luminance(hex: string): number {
  const channels = hex
    .replace("#", "")
    .match(/../g)!
    .map((h) => {
      const v = parseInt(h, 16) / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

/** Contrast ratio between two token names (1–21). */
function ratio(a: string, b: string): number {
  const la = luminance(resolveHex(a));
  const lb = luminance(resolveHex(b));
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

const AA_TEXT = 4.5; // normal-size text
const AA_UI = 3; // large text, icons, focus rings & other non-text indicators

// --- tests ------------------------------------------------------------------

describe("token contrast — body & role text (AA >= 4.5:1)", () => {
  it.each([
    ["--ink", "--paper"],
    ["--n-900", "--paper"],
    ["--n-800", "--paper"],
    ["--n-700", "--paper"],
    ["--n-600", "--paper"],
    ["--n-500", "--paper"], // muted
    ["--text", "--surface"],
    ["--text", "--surface-raised"],
    ["--text-muted", "--surface"],
    ["--text-muted", "--surface-raised"],
    ["--n-600", "--surface-sunken"], // secondary text on zebra rows
    ["--oxblood", "--paper"], // brand as text / icons
    ["--text-on-inverse", "--surface-inverse"],
  ])("%s on %s", (fg, bg) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_TEXT);
  });
});

describe("token contrast — text on primary & semantic fills (AA >= 4.5:1)", () => {
  it.each([
    ["--text-on-brand", "--brand-500"],
    ["--text-on-brand", "--brand-600"],
    ["--text-on-brand", "--brand-700"],
    ["--text-on-brand", "--success"],
    ["--text-on-brand", "--warning"],
    ["--text-on-brand", "--danger"],
    ["--text-on-brand", "--info"],
    ["--success", "--success-bg"],
    ["--warning", "--warning-bg"],
    ["--danger", "--danger-bg"],
    ["--info", "--info-bg"],
  ])("%s on %s", (fg, bg) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_TEXT);
  });
});

describe("token contrast — champagne gold is detailing, not text", () => {
  it("champagne fails small-text contrast on paper (guardrail)", () => {
    // The design rule: gold is never small body text on a light surface.
    expect(ratio("--champagne", "--paper")).toBeLessThan(AA_TEXT);
  });

  it("gold is legible on inverse surfaces", () => {
    expect(ratio("--gold-500", "--ink")).toBeGreaterThanOrEqual(AA_TEXT);
  });

  it("focus indicator meets the 3:1 non-text minimum", () => {
    expect(ratio("--focus-ring", "--surface-inverse")).toBeGreaterThanOrEqual(AA_UI);
    // light-surface ring companion used by the Phase-2 focus-visible style
    expect(ratio("--focus-ring-edge", "--paper")).toBeGreaterThanOrEqual(AA_UI);
  });
});
