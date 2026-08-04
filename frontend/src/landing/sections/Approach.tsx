// §2 — Built around your process. The "Blueprint → Workflow → Platform" motif is
// rendered as a connected three-step flow (horizontal on desktop, stacked on mobile).

import shared from "../LandingPage.module.css";
import styles from "./Approach.module.css";

const STEPS: ReadonlyArray<[string, string, string]> = [
  ["01", "Blueprint", "We map how your company actually works — every approval, department, and hand-off."],
  ["02", "Workflow", "Your stages, roles, and rules are encoded exactly as they are. Nothing forced."],
  ["03", "Platform", "The result feels like software that has always belonged inside your business."],
];

export function Approach() {
  return (
    <section id="approach" className={shared.section} aria-labelledby="approach-h">
      <div className={shared.container}>
        <div className={styles.head}>
          <p className={shared.eyebrow}>The approach</p>
          <h2 id="approach-h" className={shared.headline}>
            Built around your process.
            <span className={shared.headlineSub}>Not ours.</span>
          </h2>
          <p className={shared.lede}>
            Instead of forcing your company into predefined workflows, we map
            every approval, department, project phase, document flow, and
            responsibility before writing a single configuration.
          </p>
        </div>

        <ol className={styles.flow}>
          {STEPS.map(([num, title, body]) => (
            <li key={num} className={styles.step}>
              <span className={styles.num}>{num}</span>
              <h3 className={styles.stepTitle}>{title}</h3>
              <p className={styles.stepBody}>{body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
