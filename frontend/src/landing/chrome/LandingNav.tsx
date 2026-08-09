// LandingNav — fixed top chrome: wordmark, section anchors, a live clock, and a
// Book pill. Below the links' breakpoint the anchors collapse into a full-screen
// menu behind the MENU/close button. The bar gains a translucent backdrop once
// the page is scrolled past the hero.

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { EASE } from "../motion/variants";
import { LiveClock } from "./LiveClock";
import styles from "./LandingNav.module.css";

const LINKS: ReadonlyArray<readonly [string, string]> = [
  ["Approach", "#approach"],
  ["Platform", "#platform"],
  ["Process", "#process"],
  ["Questions", "#faq"],
];

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 32);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // Lock body scroll while the overlay is open.
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <header className={styles.nav} data-scrolled={scrolled ? "" : undefined}>
      <a href="#top" className={styles.wordmark} onClick={() => setOpen(false)}>
        Blyns
      </a>

      <nav className={styles.links} aria-label="Primary">
        {LINKS.map(([label, href]) => (
          <a key={href} href={href} className={styles.link}>
            {label}
          </a>
        ))}
      </nav>

      <div className={styles.meta}>
        <LiveClock className={styles.clock} />
        <a href="#book" className={styles.book}>
          Book a session
        </a>
        <button
          type="button"
          className={styles.menuBtn}
          aria-expanded={open}
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Close" : "Menu"}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            className={styles.overlay}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4, ease: EASE }}
          >
            <nav className={styles.overlayLinks} aria-label="Menu">
              {LINKS.map(([label, href], i) => (
                <motion.a
                  key={href}
                  href={href}
                  className={styles.overlayLink}
                  onClick={() => setOpen(false)}
                  initial={{ y: 40, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  exit={{ y: 20, opacity: 0 }}
                  transition={{ duration: 0.5, ease: EASE, delay: 0.05 * i }}
                >
                  <span className={styles.overlayIndex}>0{i + 1}</span>
                  {label}
                </motion.a>
              ))}
              <motion.a
                href="#book"
                className={`${styles.overlayLink} ${styles.overlayBook}`}
                onClick={() => setOpen(false)}
                initial={{ y: 40, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: 20, opacity: 0 }}
                transition={{ duration: 0.5, ease: EASE, delay: 0.05 * LINKS.length }}
              >
                <span className={styles.overlayIndex}>→</span>
                Book a session
              </motion.a>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
