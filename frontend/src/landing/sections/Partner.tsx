// Partner — "More than software. A long-term partner." A centered closing
// statement for the editorial run, revealed in three beats. Copy verbatim.

import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
import styles from "./Partner.module.css";

export function Partner() {
  return (
    <Section id="partner" tone="base" labelledBy="partner-h">
      <div className={`l-container ${styles.inner}`}>
        <Reveal className={styles.head}>
          <SectionLabel index="09">Beyond delivery</SectionLabel>
          <Heading id="partner-h" sub="A long-term partner." subTone="rust">
            More than software.
          </Heading>
        </Reveal>

        <Reveal delay={0.1}>
          <p className={styles.lede}>
            We don&rsquo;t disappear after deployment. We continuously refine your platform as your
            business evolves.
          </p>
        </Reveal>

        <Reveal delay={0.16}>
          <p className={styles.evolve}>
            Your processes improve. <span>Your software evolves with them.</span>
          </p>
        </Reveal>
      </div>
    </Section>
  );
}
