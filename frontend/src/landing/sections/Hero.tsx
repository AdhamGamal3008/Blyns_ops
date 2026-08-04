// Hero — full-bleed serif statement + dual CTA, with a self-contained blueprint
// panel standing in for the product screenshot wired in Phase E. Copy is verbatim
// from docs/LANDING_PAGE.md / the content brief.

import shared from "../LandingPage.module.css";
import styles from "./Hero.module.css";

export function Hero() {
  return (
    <section id="top" className={styles.hero}>
      <div className={`${shared.container} ${styles.grid}`}>
        <div className={styles.copy}>
          <p className={shared.eyebrow}>Blyns · Your company's operating system</p>

          <h1 className={styles.headline}>
            Your Company Was Built Differently.
            <span className={styles.headlineAccent}> Your Software Should Be Too.</span>
          </h1>

          <p className={styles.support}>
            Most software asks your team to change how they work. We do the
            opposite. We study your operations, approvals, teams, and projects —
            then build a management platform around the way your company actually
            runs.
          </p>

          <ul className={styles.tenets} aria-label="Our principles">
            <li>No templates.</li>
            <li>No unnecessary features.</li>
            <li>No compromises.</li>
          </ul>

          <div className={styles.actions}>
            <a href="#book" className={shared.ctaPrimary}>
              Book Your Discovery Session
            </a>
            <a href="#platform" className={shared.ctaSecondary}>
              See How It Works
            </a>
          </div>
        </div>

        {/* Blueprint panel — the §2 "Blueprint → Workflow → Platform" motif,
            rendered in CSS so the hero stands on its own before screenshots land. */}
        <div className={styles.visual} aria-hidden="true">
          <div className={styles.blueprint}>
            <span className={styles.blueprintTag}>Blueprint</span>
            <div className={styles.flow}>
              <span>Blueprint</span>
              <i />
              <span>Workflow</span>
              <i />
              <span>Platform</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
