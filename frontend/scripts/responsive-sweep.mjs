#!/usr/bin/env node
// Phase 7 acceptance: "every route is beautiful and fully operable on a 375px
// viewport; no layout breaks between 360px and 1536px."
//
// The "no layout breaks" half is mechanical, so it is measured rather than
// eyeballed: every route is loaded at each width and asserted to have no
// horizontal overflow, no control below the 44px touch target, and no text
// input under 16px (which makes iOS zoom the viewport on focus).
//
//   node scripts/responsive-sweep.mjs [baseUrl]
//
// Needs the dev server and API running, and a seeded tenant. Exits non-zero
// with a per-route report on failure.

import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:5173";
const WIDTHS = [360, 375, 390, 414, 768, 834, 1024, 1280, 1536];

const CLIENT = { company: "acme", email: "jane@acme.com", password: "LocalDev!2026" };

const ROUTES = [
  "/login",
  "/app",
  "/app/projects",
  "/app/crm",
  "/app/inventory",
  "/app/finance",
  "/app/settings",
];

/** Runs in the page. Returns everything that breaks the acceptance criteria. */
function audit() {
  const de = document.documentElement;
  const overflow = de.scrollWidth - de.clientWidth;

  // An element clipped by an ancestor scroller (a tab strip, a kanban board, a
  // wide table in its own overflow box) is contained by design — only things
  // that push the *page* itself count.
  const inScroller = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if (ox === "auto" || ox === "scroll" || ox === "hidden") return true;
    }
    return false;
  };

  const offenders = [...document.querySelectorAll("*")]
    .filter((el) => {
      const b = el.getBoundingClientRect();
      return b.width > 0 && b.right > de.clientWidth + 1 && !inScroller(el);
    })
    .slice(0, 5)
    .map((el) => `${el.tagName}.${String(el.className).split(" ")[0]}`.slice(0, 60));

  // Only controls that are actually visible and interactive.
  const visible = (el) => {
    const b = el.getBoundingClientRect();
    return b.width > 0 && b.height > 0 && getComputedStyle(el).visibility !== "hidden";
  };

  // The tap target is the whole control, which for a text field is the bordered
  // wrapper the input sits inside — so an element passes if it or its parent
  // meets the minimum.
  const targetSize = (el) => {
    const b = el.getBoundingClientRect();
    const p = el.parentElement?.getBoundingClientRect();
    return {
      w: Math.max(b.width, p?.width ?? 0),
      h: Math.max(b.height, p?.height ?? 0),
    };
  };

  const smallTargets = [...document.querySelectorAll("button,a[href],input,select,[role=tab]")]
    .filter(visible)
    .filter((el) => {
      // a radio rendered as a swatch inside a bigger label is fine
      if (el.type === "radio" || el.type === "checkbox") return false;
      const { w, h } = targetSize(el);
      return Math.min(h, w) < 44;
    })
    .slice(0, 6)
    .map((el) => {
      const { w, h } = targetSize(el);
      const label = (el.textContent || el.getAttribute("aria-label") || el.tagName).trim();
      return `${label.slice(0, 24)} ${Math.round(w)}x${Math.round(h)}`;
    });

  const smallText = [...document.querySelectorAll("input,select,textarea")]
    .filter(visible)
    .filter((el) => parseFloat(getComputedStyle(el).fontSize) < 16)
    .slice(0, 6)
    .map((el) => `${el.placeholder || el.name || el.tagName}@${getComputedStyle(el).fontSize}`);

  return { overflow, offenders, smallTargets, smallText };
}

const browser = await chromium.launch();
const context = await browser.newContext({ hasTouch: true, isMobile: false });
const page = await context.newPage();

// sign in once; the token lives in localStorage and rides along
await page.goto(`${BASE}/login`);
await page.fill('input[placeholder="acme"]', CLIENT.company);
await page.fill('input[type="email"]', CLIENT.email);
await page.fill('input[type="password"]', CLIENT.password);
await page.click('button[type="submit"]');
await page.waitForURL("**/app", { timeout: 10_000 });

const failures = [];
for (const width of WIDTHS) {
  await page.setViewportSize({ width, height: 900 });
  for (const route of ROUTES) {
    await page.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(250);
    const r = await page.evaluate(audit);

    const problems = [];
    if (r.overflow > 0) problems.push(`overflows ${r.overflow}px [${r.offenders.join(", ")}]`);
    // touch targets only matter where a finger is the pointer
    if (width <= 834 && r.smallTargets.length) {
      problems.push(`targets <44px: ${r.smallTargets.join("; ")}`);
    }
    if (width <= 834 && r.smallText.length) {
      problems.push(`inputs <16px (iOS zoom): ${r.smallText.join("; ")}`);
    }
    if (problems.length) failures.push(`${width}px ${route}\n    ${problems.join("\n    ")}`);
  }
  process.stdout.write(`  ${width}px checked\n`);
}

await browser.close();

if (failures.length) {
  console.error(`\n✗ ${failures.length} responsive failure(s):\n`);
  for (const f of failures) console.error(`  ${f}\n`);
  process.exit(1);
}
console.log(`\n✓ ${ROUTES.length} routes clean across ${WIDTHS.join(", ")}px`);
