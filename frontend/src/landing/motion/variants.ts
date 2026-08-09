// Shared motion tokens for the landing. One easing + a couple of variant
// factories keep every section's entrance consistent. Kept framework-thin so
// each primitive stays small and reduced-motion aware.

import type { Variants } from "framer-motion";

/** easeOutExpo-ish — the CSS mirror lives in theme.css as --l-ease. */
export const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];
export const EASE_INOUT: [number, number, number, number] = [0.76, 0, 0.24, 1];

/** Fade + rise. Used by <Reveal> and as a child variant in staggered groups. */
export const riseVariants: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.8, ease: EASE } },
};

/** Parent that staggers its children's `visible` transition. */
export const staggerContainer = (stagger = 0.08, delay = 0): Variants => ({
  hidden: {},
  visible: { transition: { staggerChildren: stagger, delayChildren: delay } },
});
