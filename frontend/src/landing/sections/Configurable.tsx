// Configurable — "Nothing is generic. Everything is configurable." A tentpole:
// the deepest tone, and an infinite marquee of "Every field ✳ Every workflow ✳ …"
// that maps 1:1 to the template's material ribbon. Copy verbatim.

import { Marquee, Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
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
    <Section id="configurable" tone="deep" labelledBy="configurable-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="04">No compromises</SectionLabel>
          <Heading id="configurable-h" sub="Everything is configurable." subTone="rust">
            Nothing is generic.
          </Heading>
        </Reveal>
      </div>

      <div className={styles.marqueeWrap} aria-hidden="true">
        <Marquee speed={38}>
          {EVERY.map((word) => (
            <span key={word} className={styles.item}>
              Every {word}
              <span className={styles.star}>✳</span>
            </span>
          ))}
        </Marquee>
      </div>

      <div className="l-container">
        <Reveal>
          <p className={styles.close}>Configured specifically for your company.</p>
        </Reveal>
      </div>
    </Section>
  );
}
