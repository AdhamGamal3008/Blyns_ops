// Growth — "Built for growing companies." A two-column narrative: the thesis on
// the left, the compounding pressures rising in on the right. Copy verbatim.

import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
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
    <Section id="growth" tone="raised" labelledBy="growth-h">
      <div className={`l-container ${styles.grid}`}>
        <Reveal className={styles.intro}>
          <div className={styles.head}>
            <SectionLabel index="07">Why tailored</SectionLabel>
            <Heading id="growth-h">Built for growing companies.</Heading>
          </div>
          <p className={styles.lede}>As your company grows, the pressure compounds.</p>
        </Reveal>

        <div>
          <ul className={styles.pressures}>
            {PRESSURES.map((line, i) => (
              <Reveal as="li" key={line} className={styles.pressure} delay={i * 0.07}>
                <span className={styles.pIndex}>0{i + 1}</span>
                {line}
              </Reveal>
            ))}
          </ul>
          <Reveal>
            <p className={styles.close}>
              That&rsquo;s where a tailored platform becomes your competitive advantage.
            </p>
          </Reveal>
        </div>
      </div>
    </Section>
  );
}
