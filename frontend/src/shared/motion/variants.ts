// Shared Framer variants, so every animated surface rises and fades by the
// same amount. Anything bespoke should have a reason written next to it.

import type { Variants } from "framer-motion";
import { DUR, EASE, ROUTE_IN, ROUTE_OUT } from "./durations";

/** Page/route change: crossfade with a slight rise. */
export function routeVariants(reduced: boolean): Variants {
  if (reduced) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1, transition: { duration: 0 } },
      exit: { opacity: 0, transition: { duration: 0 } },
    };
  }
  return {
    initial: { opacity: 0, y: 6 },
    animate: {
      opacity: 1,
      y: 0,
      transition: { duration: ROUTE_IN / 1000, ease: EASE.out },
    },
    exit: {
      opacity: 0,
      y: -4,
      transition: { duration: ROUTE_OUT / 1000, ease: EASE.out },
    },
  };
}

// Overlay choreography. Every layered surface — dialog, sheet, mobile drawer,
// command palette — uses these two, so the scrim and the panel move at the same
// speed everywhere instead of each overlay picking its own literal.

/** The scrim behind a layered surface. Fades only. */
export function overlayTransition(reduced: boolean) {
  return { duration: reduced ? 0 : DUR.fast / 1000 };
}

/** The panel itself. Slower than its scrim, so the surface leads the eye. */
export function contentTransition(reduced: boolean) {
  return { duration: reduced ? 0 : DUR.base / 1000, ease: EASE.out };
}

/** A single element rising into place — used by the rail's arriving gate. */
export function riseVariants(reduced: boolean): Variants {
  return {
    initial: reduced ? { opacity: 1 } : { opacity: 0, y: 4 },
    animate: {
      opacity: 1,
      y: 0,
      transition: { duration: reduced ? 0 : DUR.base / 1000, ease: EASE.out },
    },
  };
}
