// Lifecycle — "From opportunity to completion." The real 9-stage project journey
// as a pinned, scroll-driven horizontal track: as you scroll the tall section,
// the timeline slides sideways through the stages. Reduced motion falls back to a
// plain horizontal swipe strip. Copy verbatim.

import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useLayoutEffect, useRef, useState } from "react";
import { Heading, SectionLabel } from "../ui";
import styles from "./Lifecycle.module.css";

const STAGES: readonly string[] = [
  "Lead",
  "Quotation",
  "Design",
  "Approval",
  "Procurement",
  "Production",
  "Installation",
  "Handover",
  "After Sales",
];

function Nodes() {
  return (
    <>
      {STAGES.map((stage, i) => (
        <li key={stage} className={styles.node}>
          <span className={styles.dot} aria-hidden="true" />
          <span className={styles.nodeIndex}>{String(i + 1).padStart(2, "0")}</span>
          <span className={styles.nodeName}>{stage}</span>
        </li>
      ))}
    </>
  );
}

export function Lifecycle() {
  const reduce = useReducedMotion();
  const sectionRef = useRef<HTMLElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLOListElement>(null);
  const [distance, setDistance] = useState(0);

  useLayoutEffect(() => {
    const track = trackRef.current;
    const viewport = viewportRef.current;
    if (!track || !viewport) return;
    const measure = () => setDistance(Math.max(0, track.scrollWidth - viewport.clientWidth));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(track);
    ro.observe(viewport);
    return () => ro.disconnect();
  }, []);

  const { scrollYProgress } = useScroll({ target: sectionRef, offset: ["start start", "end end"] });
  const x = useTransform(scrollYProgress, [0, 1], [0, -distance]);

  const heading = (
    <div className={`l-container ${styles.head}`}>
      <SectionLabel index="06">The journey</SectionLabel>
      <Heading id="lifecycle-h">From opportunity to completion.</Heading>
    </div>
  );
  const close = (
    <div className="l-container">
      <p className={styles.close}>
        Entire lifecycle. <span>One connected platform.</span>
      </p>
    </div>
  );

  if (reduce) {
    return (
      <section id="lifecycle" className={`${styles.section} ${styles.static}`} aria-labelledby="lifecycle-h">
        {heading}
        <div className={styles.swipe}>
          <ol className={styles.track}>
            <Nodes />
          </ol>
        </div>
        {close}
      </section>
    );
  }

  return (
    <section
      ref={sectionRef}
      id="lifecycle"
      className={styles.section}
      style={{ height: distance ? `calc(100svh + ${distance}px)` : "100svh" }}
      aria-labelledby="lifecycle-h"
    >
      <div className={styles.sticky}>
        {heading}
        <div ref={viewportRef} className={styles.viewport}>
          <motion.ol ref={trackRef} className={styles.track} style={{ x }}>
            <Nodes />
          </motion.ol>
        </div>
        {close}
      </div>
    </section>
  );
}
