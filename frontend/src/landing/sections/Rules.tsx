// §6 — Your business. Your rules. The emotional peak: each need answered "Done."

import shared from "../LandingPage.module.css";
import styles from "./Rules.module.css";

const NEEDS: readonly string[] = [
  "Need three approval levels?",
  "Need different workflows for flooring and furniture?",
  "Need procurement to work differently from execution?",
  "Need different dashboards for every department?",
  "Need multiple companies under one platform?",
];

export function Rules() {
  return (
    <section id="rules" className={shared.section} aria-labelledby="rules-h">
      <div className={shared.container}>
        <p className={shared.eyebrow}>Your rules</p>
        <h2 id="rules-h" className={styles.headline}>
          Your business.
          <span className={styles.headlineSub}>Your rules.</span>
        </h2>

        <dl className={styles.pairs}>
          {NEEDS.map((need) => (
            <div key={need} className={styles.pair}>
              <dt className={styles.need}>{need}</dt>
              <dd className={styles.done}>Done.</dd>
            </div>
          ))}
        </dl>

        <p className={styles.close}>
          We don't ask you to adapt. <span>We adapt to you.</span>
        </p>
      </div>
    </section>
  );
}
