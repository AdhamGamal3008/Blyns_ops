// Preloader — the first impression. A counter races 000 → 100 beneath the
// wordmark, a rust progress line fills, then the whole panel wipes up to reveal
// the hero. Shows once per tab session (sessionStorage); collapses to a brief
// hold under reduced motion. Calls onDone when the hero is allowed to animate in.

import { animate, AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { EASE, EASE_INOUT } from "../motion/variants";
import styles from "./Preloader.module.css";

export const PRELOAD_KEY = "blyns-landing-preloaded";

function alreadyRan() {
  return typeof window !== "undefined" && window.sessionStorage.getItem(PRELOAD_KEY) === "1";
}

export function Preloader({ onDone }: { onDone: () => void }) {
  const reduce = useReducedMotion();
  const [done, setDone] = useState(alreadyRan);
  const [count, setCount] = useState(() => (alreadyRan() ? 100 : 0));
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  useEffect(() => {
    if (done) {
      onDoneRef.current();
      return;
    }
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      window.sessionStorage.setItem(PRELOAD_KEY, "1");
      onDoneRef.current();
      setDone(true);
    };

    if (reduce) {
      setCount(100);
      const t = window.setTimeout(finish, 450);
      return () => window.clearTimeout(t);
    }

    const controls = animate(0, 100, {
      duration: 1.6,
      ease: EASE,
      onUpdate: (v) => setCount(Math.round(v)),
      onComplete: () => window.setTimeout(finish, 280),
    });
    return () => controls.stop();
  }, [done, reduce]);

  return (
    <AnimatePresence>
      {!done && (
        <motion.div
          className={styles.screen}
          initial={{ y: 0 }}
          exit={{ y: "-100%" }}
          transition={{ duration: 0.9, ease: EASE_INOUT }}
        >
          <div className={styles.inner}>
            <span className={styles.word}>Blyns</span>
            <span className={styles.count}>{String(count).padStart(3, "0")}</span>
          </div>
          <div className={styles.barTrack}>
            <span className={styles.bar} style={{ transform: `scaleX(${count / 100})` }} />
          </div>
          <span className={styles.meta}>Your company&rsquo;s operating system</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
