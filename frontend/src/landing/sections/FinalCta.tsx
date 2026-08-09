// Final CTA — the invitation + the discovery-booking form (the page's one
// functional feature). The closing tentpole, on the deepest tone with a rust
// wash. Copy verbatim.

import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
import { BookingForm } from "./BookingForm";
import styles from "./FinalCta.module.css";

export function FinalCta() {
  return (
    <Section id="book" tone="deep" labelledBy="book-h" className={styles.section}>
      <div className={`l-container ${styles.grid}`}>
        <Reveal className={styles.copy}>
          <SectionLabel>Let&rsquo;s begin</SectionLabel>
          <Heading id="book-h" sub="Why should your software be?" subTone="rust">
            Your company isn&rsquo;t standard.
          </Heading>
          <p className={styles.lede}>
            Every successful project starts with understanding the brief. Let&rsquo;s start with
            yours.
          </p>
        </Reveal>

        <Reveal delay={0.1} className={styles.formCard}>
          <p className={styles.formTitle}>Book a discovery session</p>
          <BookingForm />
        </Reveal>
      </div>
    </Section>
  );
}
