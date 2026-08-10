import "@testing-library/jest-dom";
import { expect } from "vitest";
import * as axeMatchers from "vitest-axe/matchers";

// `toHaveNoViolations` for the a11y tests. axe runs in jsdom, which has no
// layout engine, so it checks structure and ARIA — names, roles, relationships,
// duplicate ids — not colour contrast. Contrast is covered separately and
// exactly by contrast.test.ts against the tokens.
expect.extend(axeMatchers);

// jsdom ships no ResizeObserver either. Radix measures its indicator through
// `react-use-size` (Checkbox, Switch), which constructs one on mount and throws
// without it. Nothing in jsdom lays out, so a no-op observer is the honest stub.
if (typeof globalThis.ResizeObserver !== "function") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// jsdom implements no layout, so Element.scrollIntoView is absent. Tabs calls it
// on mount to bring the active trigger into view; a no-op is the honest stub
// (there is nothing to scroll) and keeps any Tabs-mounting test from throwing.
if (typeof Element !== "undefined" && typeof Element.prototype.scrollIntoView !== "function") {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom ships no IntersectionObserver. framer-motion's useInView (the landing's
// <Reveal> entrances and the lazily-mounted Platform screens) constructs one on
// mount; a no-op observer that never fires keeps those components mounted at
// their initial state — findable by text — without throwing.
if (typeof globalThis.IntersectionObserver !== "function") {
  globalThis.IntersectionObserver = class {
    readonly root = null;
    readonly rootMargin = "";
    readonly thresholds: ReadonlyArray<number> = [];
    constructor() {}
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  } as unknown as typeof IntersectionObserver;
}

// jsdom ships no matchMedia. Components read it to decide whether to animate,
// so provide a real-shaped stub that reports "no preference"; a test that cares
// about reduced motion overrides `matches` for the query it is exercising.
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
