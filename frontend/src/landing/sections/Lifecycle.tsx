// §7 — From opportunity to completion. The real project lifecycle as a connected
// timeline (horizontal on desktop, vertical on mobile).

import shared from "../LandingPage.module.css";
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

export function Lifecycle() {
  return (
    <section
      id="lifecycle"
      className={`${shared.section} ${shared.sectionSunken}`}
      aria-labelledby="lifecycle-h"
    >
      <div className={shared.container}>
        <p className={shared.eyebrow}>The journey</p>
        <h2 id="lifecycle-h" className={shared.headline}>
          From opportunity to completion.
        </h2>

        <ol className={styles.track}>
          {STAGES.map((stage, i) => (
            <li key={stage} className={styles.node}>
              <span className={styles.dot}>{i + 1}</span>
              <span className={styles.label}>{stage}</span>
            </li>
          ))}
        </ol>

        <p className={styles.close}>
          Entire lifecycle. <span>One connected platform.</span>
        </p>
      </div>
    </section>
  );
}
