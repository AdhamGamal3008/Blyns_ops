// Rules — "Your business. Your rules." The emotional peak: each need is answered
// with an italic rust "Done." that reveals on scroll. Copy verbatim.

import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
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
    <Section id="rules" tone="base" labelledBy="rules-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="05">Your rules</SectionLabel>
          <Heading id="rules-h" sub="Your rules." subTone="rust">
            Your business.
          </Heading>
        </Reveal>

        <dl className={styles.pairs}>
          {NEEDS.map((need, i) => (
            <Reveal as="div" key={need} className={styles.pair} delay={i * 0.06}>
              <dt className={styles.need}>{need}</dt>
              <dd className={styles.done}>Done.</dd>
            </Reveal>
          ))}
        </dl>

        <Reveal>
          <p className={styles.close}>
            We don&rsquo;t ask you to adapt. <span>We adapt to you.</span>
          </p>
        </Reveal>
      </div>
    </Section>
  );
}
