// Sticky top navigation for the public landing page. Plain in-page anchors
// (the design system already sets `scroll-behavior: smooth` on <html>), so the
// nav needs no router — it never leaves `/`. Reuses the shared CTA styles.

import shared from "../LandingPage.module.css";
import styles from "./LandingNav.module.css";

const LINKS: ReadonlyArray<{ href: string; label: string }> = [
  { href: "#approach", label: "Approach" },
  { href: "#platform", label: "Platform" },
  { href: "#process", label: "Process" },
  { href: "#security", label: "Security" },
  { href: "#faq", label: "FAQ" },
];

export function LandingNav() {
  return (
    <header className={styles.header}>
      <div className={styles.bar}>
        <a href="#top" className={styles.brand} aria-label="Blyns — home">
          Blyns<span className={styles.mark} aria-hidden="true" />
        </a>

        <nav className={styles.links} aria-label="Sections">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} className={styles.link}>
              {link.label}
            </a>
          ))}
        </nav>

        <a href="#book" className={`${shared.ctaPrimary} ${styles.cta}`}>
          Book a Discovery Session
        </a>
      </div>
    </header>
  );
}
