// Typed references to the design tokens defined in tokens.css.
//
// These are CSS `var(--x)` strings, not literal hex — tokens.css stays the
// single source of truth. Use them for JS consumers that need a token value:
// chart series (Recharts/visx), Framer Motion transitions, inline styles.
// For a resolved literal value at runtime (e.g. "#8C1D24"), use readToken().

export const palette = {
  paper: "var(--paper)",
  ink: "var(--ink)",
  oxblood: "var(--oxblood)",
  champagne: "var(--champagne)",
} as const;

export const brand = {
  700: "var(--brand-700)",
  600: "var(--brand-600)",
  500: "var(--brand-500)",
  400: "var(--brand-400)",
  300: "var(--brand-300)",
  50: "var(--brand-50)",
} as const;

export const gold = {
  700: "var(--gold-700)",
  600: "var(--gold-600)",
  500: "var(--gold-500)",
  400: "var(--gold-400)",
  300: "var(--gold-300)",
  50: "var(--gold-50)",
} as const;

export const neutral = {
  900: "var(--n-900)",
  800: "var(--n-800)",
  700: "var(--n-700)",
  600: "var(--n-600)",
  500: "var(--n-500)",
  400: "var(--n-400)",
  300: "var(--n-300)",
  200: "var(--n-200)",
  100: "var(--n-100)",
  50: "var(--n-50)",
} as const;

export const semantic = {
  success: "var(--success)",
  successBg: "var(--success-bg)",
  warning: "var(--warning)",
  warningBg: "var(--warning-bg)",
  danger: "var(--danger)",
  dangerBg: "var(--danger-bg)",
  info: "var(--info)",
  infoBg: "var(--info-bg)",
} as const;

export const motion = {
  duration: {
    instant: "var(--dur-instant)",
    fast: "var(--dur-fast)",
    base: "var(--dur-base)",
    slow: "var(--dur-slow)",
    page: "var(--dur-page)",
  },
  ease: {
    out: "var(--ease-out)",
    inOut: "var(--ease-inout)",
  },
} as const;

/**
 * Resolve a CSS custom property to its computed value in the browser
 * (e.g. readToken("--oxblood") -> "#8C1D24"). Returns "" outside the browser.
 */
export function readToken(name: string): string {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
