// §8 — Built for growing companies. Narrative + an escalating list of pressures.

import shared from "../LandingPage.module.css";
import styles from "./Growth.module.css";

const PRESSURES: readonly string[] = [
  "Departments multiply.",
  "Projects become larger.",
  "Teams become harder to coordinate.",
  "Approvals slow everything down.",
  "Information becomes scattered.",
];

export function Growth() {
  return (
    <section id="growth" className={shared.section} aria-labelledby="growth-h">
      <div className={`${shared.container} ${styles.grid}`}>
        <div>
          <p className={shared.eyebrow}>Why tailored</p>
          <h2 id="growth-h" className={shared.headline}>
            Built for growing companies.
          </h2>
          <p className={shared.lede}>As your company grows, the pressure compounds.</p>
        </div>

        <div>
          <ul className={shared.statementList}>
            {PRESSURES.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className={styles.close}>
            That's where a tailored platform becomes your competitive advantage.
          </p>
        </div>
      </div>
    </section>
  );
}
