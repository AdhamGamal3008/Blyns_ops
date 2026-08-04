// §11 — How we build your platform. Six numbered steps.

import shared from "../LandingPage.module.css";
import styles from "./Process.module.css";

const STEPS: ReadonlyArray<[string, string, string]> = [
  ["01", "Discovery", "Understanding how your business truly works."],
  ["02", "Process Mapping", "Every workflow documented."],
  ["03", "Platform Design", "Tailored around your operations."],
  ["04", "Configuration", "Modules adapted to your company."],
  ["05", "Training", "Every team prepared."],
  ["06", "Continuous Evolution", "Your platform grows with your business."],
];

export function Process() {
  return (
    <section
      id="process"
      className={`${shared.section} ${shared.sectionAlt}`}
      aria-labelledby="process-h"
    >
      <div className={shared.container}>
        <p className={shared.eyebrow}>How we build</p>
        <h2 id="process-h" className={shared.headline}>
          How we build your platform.
        </h2>

        <ol className={styles.grid}>
          {STEPS.map(([num, title, body]) => (
            <li key={num} className={styles.step}>
              <span className={styles.num}>{num}</span>
              <h3 className={styles.title}>{title}</h3>
              <p className={styles.body}>{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
