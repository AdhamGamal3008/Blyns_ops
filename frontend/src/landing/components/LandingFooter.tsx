// Dark footer that bookends the page. Real anchors only — no placeholder social
// accounts. The final CTA also lives here so the page always ends on the invite.

import shared from "../LandingPage.module.css";
import styles from "./LandingFooter.module.css";

const YEAR = new Date().getFullYear();

export function LandingFooter() {
  return (
    <footer className={styles.footer}>
      <div className={`${shared.container} ${styles.inner}`}>
        <div className={styles.lead}>
          <p className={styles.wordmark}>
            Blyns<span className={styles.mark} aria-hidden="true" />
          </p>
          <p className={styles.tagline}>
            The system behind exceptional projects — engineered around the way
            your company actually runs.
          </p>
          <a href="#book" className={`${shared.ctaPrimary} ${styles.cta}`}>
            Book a Discovery Session
          </a>
        </div>

        <nav className={styles.nav} aria-label="Footer">
          <a href="#approach">Approach</a>
          <a href="#platform">Platform</a>
          <a href="#process">Process</a>
          <a href="#security">Security</a>
          <a href="#faq">FAQ</a>
        </nav>
      </div>

      <div className={`${shared.container} ${styles.legal}`}>
        <span>© {YEAR} Blyns. All rights reserved.</span>
        <span className={styles.realm}>
          <a href="/login">Company sign-in</a>
          <a href="/admin/login">Operator sign-in</a>
        </span>
      </div>
    </footer>
  );
}
