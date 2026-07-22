// The motion budget, in milliseconds.
//
// These mirror the `--dur-*` custom properties in design/tokens.css. CSS owns
// the values for anything styled in CSS; this file exists because some motion
// is driven from JS (Framer variants, Recharts' animationDuration) and cannot
// read a custom property. `motion.test.ts` parses tokens.css and fails if the
// two ever drift, so there is still exactly one source of truth.

export const DUR = {
  instant: 80,
  fast: 140,
  base: 220,
  slow: 360,
  /** The ceiling. Phase 6's acceptance: no animation may exceed this. */
  page: 480,
} as const;

/** Token easings, as Framer-compatible cubic-bezier arrays. */
export const EASE = {
  out: [0.2, 0, 0, 1],
  inOut: [0.4, 0, 0.2, 1],
} as const;

/** Route transition: out + in must fit inside the page budget. */
export const ROUTE_OUT = DUR.fast + 40; // 180
export const ROUTE_IN = DUR.base; // 220
