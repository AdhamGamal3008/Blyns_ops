// Approach — "Built around your process. Not ours." The lede uses the signature
// word-by-word reveal; the Blueprint → Workflow → Platform steps rise in on scroll.
// Copy verbatim from the brief.

import { Reveal, WordReveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
import styles from "./Approach.module.css";

const STEPS: ReadonlyArray<[string, string, string]> = [
  ["01", "Blueprint", "We map how your company actually works — every approval, department, and hand-off."],
  ["02", "Workflow", "Your stages, roles, and rules are encoded exactly as they are. Nothing forced."],
  ["03", "Platform", "The result feels like software that has always belonged inside your business."],
];

export function Approach() {
  return (
    <Section id="approach" tone="base" labelledBy="approach-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="01">The approach</SectionLabel>
          <Heading id="approach-h" sub="Not ours.">
            Built around your process.
          </Heading>
        </Reveal>

        <p className={styles.lede}>
          <WordReveal text="Instead of forcing your company into predefined workflows, we map every approval, department, project phase, document flow, and responsibility before writing a single configuration." />
        </p>

        <ol className={styles.steps}>
          {STEPS.map(([num, title, body], i) => (
            <Reveal as="li" key={num} className={styles.step} delay={i * 0.08}>
              <span className={styles.num}>{num}</span>
              <h3 className={styles.stepTitle}>{title}</h3>
              <p className={styles.stepBody}>{body}</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </Section>
  );
}
