// Reveal — fade + rise as the element scrolls into view. The workhorse
// entrance used across every section. No-ops under prefers-reduced-motion.

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { EASE } from "./variants";

type RevealTag = "div" | "section" | "span" | "li" | "p" | "h2" | "h3" | "article" | "ul" | "ol";

type RevealProps = {
  children: ReactNode;
  className?: string;
  delay?: number;
  y?: number;
  once?: boolean;
  as?: RevealTag;
};

export function Reveal({
  children,
  className,
  delay = 0,
  y = 24,
  once = true,
  as = "div",
}: RevealProps) {
  const reduce = useReducedMotion();
  const MotionTag = motion[as] as typeof motion.div;

  return (
    <MotionTag
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      whileInView={reduce ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once, margin: "0px 0px -12% 0px" }}
      transition={{ duration: 0.8, ease: EASE, delay }}
    >
      {children}
    </MotionTag>
  );
}
