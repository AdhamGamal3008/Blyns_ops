// True only for the first moments after a surface mounts.
//
// Entrance motion should play when a surface first appears and never again —
// re-sorting a table or flipping a page is a *rearrangement*, and re-running an
// entrance there makes routine interaction feel like a reload. Callers drop the
// entrance class once this goes false, so later renders are inert.

import { useEffect, useState } from "react";

import { DUR } from "./durations";

/** Entrance window: the longest stagger delay plus the animation itself. */
const WINDOW_MS = 140 + DUR.base;

export function useFirstPaint(): boolean {
  const [first, setFirst] = useState(true);

  // No mounted-once ref guard here: StrictMode double-invokes effects in dev,
  // and a guard would let the second invocation return before scheduling,
  // leaving the entrance class on forever.
  useEffect(() => {
    const t = setTimeout(() => setFirst(false), WINDOW_MS);
    return () => clearTimeout(t);
  }, []);

  return first;
}
