// WordReveal — the signature editorial effect: a block of text whose words rise
// and fade in one after another as it enters view (see the Approach section).
// The full string is exposed to assistive tech via aria-label; the animated
// words are aria-hidden. Falls back to plain text under reduced motion.

import { motion, useReducedMotion } from "framer-motion";
import { EASE } from "./variants";

type WordRevealProps = {
  text: string;
  className?: string;
  stagger?: number;
};

export function WordReveal({ text, className, stagger = 0.03 }: WordRevealProps) {
  const reduce = useReducedMotion();
  if (reduce) return <span className={className}>{text}</span>;

  const words = text.split(" ");
  return (
    <span className={className}>
      {/* Real, space-separated copy for assistive tech + selection; the animated
          words below are decorative and hidden from the a11y tree. */}
      <span className="l-sr-only">{text}</span>
      <motion.span
        aria-hidden="true"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "0px 0px -20% 0px" }}
        transition={{ staggerChildren: stagger }}
      >
        {words.map((word, i) => (
          <span
            key={`${word}-${i}`}
            style={{ display: "inline-block", overflow: "hidden", marginRight: "0.25em" }}
          >
            <motion.span
              style={{ display: "inline-block", willChange: "transform" }}
              variants={{ hidden: { y: "110%", opacity: 0 }, visible: { y: 0, opacity: 1 } }}
              transition={{ duration: 0.6, ease: EASE }}
            >
              {word}
            </motion.span>
          </span>
        ))}
      </motion.span>
    </span>
  );
}
