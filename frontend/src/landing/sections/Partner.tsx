// §10 — More than software. A long-term partner. Centered narrative.

import shared from "../LandingPage.module.css";
import styles from "./Partner.module.css";

export function Partner() {
  return (
    <section id="partner" className={shared.section} aria-labelledby="partner-h">
      <div className={`${shared.container} ${styles.inner}`}>
        <p className={shared.eyebrow}>Beyond delivery</p>
        <h2 id="partner-h" className={shared.headline}>
          More than software.
          <span className={shared.headlineSub}>A long-term partner.</span>
        </h2>
        <p className={shared.lede}>
          We don't disappear after deployment. We continuously refine your
          platform as your business evolves.
        </p>
        <p className={styles.evolve}>
          Your processes improve. <span>Your software evolves with them.</span>
        </p>
      </div>
    </section>
  );
}
