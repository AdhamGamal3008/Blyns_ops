// Process — "How we build your platform." Six numbered steps from first
// conversation to continuous evolution. Copy verbatim.

import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
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
    <Section id="process" tone="raised" labelledBy="process-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="10">How we build</SectionLabel>
          <Heading id="process-h">How we build your platform.</Heading>
        </Reveal>

        <ol className={styles.grid}>
          {STEPS.map(([num, title, body], i) => (
            <Reveal as="li" key={num} className={styles.step} delay={i * 0.06}>
              <span className={styles.num}>{num}</span>
              <h3 className={styles.title}>{title}</h3>
              <p className={styles.body}>{body}</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </Section>
  );
}
