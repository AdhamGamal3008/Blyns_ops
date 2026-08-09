// Magnetic — the element drifts toward the cursor and springs back on leave.
// Wraps pill CTAs and the menu button for that tactile studio feel. Inert under
// reduced motion and on touch (no hover), where the springs simply never fire.

import { motion, useMotionValue, useReducedMotion, useSpring } from "framer-motion";
import { type ReactNode, useRef } from "react";

type MagneticProps = {
  children: ReactNode;
  className?: string;
  /** Fraction of the cursor offset the element follows (0–1). */
  strength?: number;
};

export function Magnetic({ children, className, strength = 0.35 }: MagneticProps) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const sx = useSpring(x, { stiffness: 200, damping: 15, mass: 0.3 });
  const sy = useSpring(y, { stiffness: 200, damping: 15, mass: 0.3 });

  function onMove(e: React.MouseEvent<HTMLSpanElement>) {
    if (reduce || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    x.set((e.clientX - (r.left + r.width / 2)) * strength);
    y.set((e.clientY - (r.top + r.height / 2)) * strength);
  }
  function reset() {
    x.set(0);
    y.set(0);
  }

  return (
    <motion.span
      ref={ref}
      className={className}
      onMouseMove={onMove}
      onMouseLeave={reset}
      style={{ x: sx, y: sy, display: "inline-flex" }}
    >
      {children}
    </motion.span>
  );
}
