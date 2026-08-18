// LandingFooter — bookends the page: tagline + return CTA, real navigation and
// sign-in anchors (no placeholder socials), an oversized wordmark that returns to
// top, and the legal line. Copy carried over from the original footer.

import styles from "./LandingFooter.module.css";

const NAV: ReadonlyArray<readonly [string, string]> = [
  ["Approach", "#approach"],
  ["Platform", "#platform"],
  ["Process", "#process"],
  ["Security", "#security"],
  ["Questions", "#faq"],
];

const YEAR = new Date().getFullYear();

export function LandingFooter() {
  return (
    <footer className={styles.footer}>
      <div className={`l-container ${styles.top}`}>
        <div className={styles.lead}>
          <p className={styles.tagline}>
            The system behind exceptional projects — engineered around the way your company actually
            runs.
          </p>
          <a href="#book" className={styles.cta}>
            Book a discovery session <span aria-hidden="true">→</span>
          </a>
        </div>

        <div className={styles.cols}>
          <nav className={styles.nav} aria-label="Footer">
            <span className={styles.navHead}>Navigate</span>
            {NAV.map(([label, href]) => (
              <a key={href} href={href}>
                {label}
              </a>
            ))}
          </nav>
        </div>
      </div>

      <a href="#top" className={styles.bigMark}>
        Blyns
      </a>

      <div className={`l-container ${styles.legal}`}>
        <span>© {YEAR} Blyns. All rights reserved.</span>
        <a href="#top" className={styles.toTop}>
          Back to top <span aria-hidden="true">↑</span>
        </a>
      </div>
    </footer>
  );
}
