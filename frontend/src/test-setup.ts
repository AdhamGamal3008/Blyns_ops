import "@testing-library/jest-dom";

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
