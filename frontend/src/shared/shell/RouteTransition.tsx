// Route changes crossfade with a slight rise instead of snapping.
//
// `useOutlet()` is captured per-location and keyed on the pathname so the
// outgoing screen stays mounted long enough to animate out — rendering <Outlet>
// directly would swap its contents instantly and there would be nothing to
// exit. `mode="wait"` keeps the two screens from overlapping, which on a dense
// table view reads as a flicker.

import { AnimatePresence, motion } from "framer-motion";
import { useLocation, useOutlet } from "react-router-dom";
import { routeVariants, useReducedMotion } from "../motion";
import styles from "./RouteTransition.module.css";

export interface RouteTransitionProps {
  /** Forwarded to the routed screen via useOutletContext. */
  context?: unknown;
}

export function RouteTransition({ context }: RouteTransitionProps) {
  const location = useLocation();
  const outlet = useOutlet(context);
  const reduced = useReducedMotion();

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        // the module segment, not the full path: paging within a module should
        // not replay the transition, but moving between modules should
        key={location.pathname.split("/").slice(0, 3).join("/")}
        className={styles.root}
        variants={routeVariants(reduced)}
        initial="initial"
        animate="animate"
        exit="exit"
      >
        {outlet}
      </motion.div>
    </AnimatePresence>
  );
}
