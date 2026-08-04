// §5 — Nothing is generic. Everything is configurable. A dark, big-type break.

import shared from "../LandingPage.module.css";
import styles from "./Configurable.module.css";

const EVERY: readonly string[] = [
  "field",
  "workflow",
  "approval",
  "dashboard",
  "report",
  "permission",
  "notification",
];

export function Configurable() {
  return (
    <section
      id="configurable"
      className={`${shared.section} ${shared.sectionInk}`}
      aria-labelledby="configurable-h"
    >
      <div className={shared.container}>
        <p className={`${shared.eyebrow} ${shared.eyebrowInk}`}>No compromises</p>
        <h2
          id="configurable-h"
          className={`${shared.headline} ${shared.headlineInk}`}
        >
          Nothing is generic.
          <span className={shared.headlineSub}>Everything is configurable.</span>
        </h2>

        <ul className={styles.list}>
          {EVERY.map((word) => (
            <li key={word} className={styles.item}>
              <span className={styles.every}>Every</span> {word}.
            </li>
          ))}
        </ul>

        <p className={styles.close}>Configured specifically for your company.</p>
      </div>
    </section>
  );
}
