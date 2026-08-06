// Final CTA — the invitation + the discovery-booking form (the page's one
// functional feature).

import shared from "../LandingPage.module.css";
import { BookingForm } from "./BookingForm";
import styles from "./FinalCta.module.css";

export function FinalCta() {
  return (
    <section
      id="book"
      className={`${shared.section} ${shared.sectionGold}`}
      aria-labelledby="book-h"
    >
      <div className={`${shared.container} ${styles.grid}`}>
        <div className={styles.copy}>
          <p className={shared.eyebrow}>Let's begin</p>
          <h2 id="book-h" className={styles.headline}>
            Your company isn't standard.
            <span className={styles.headlineSub}>Why should your software be?</span>
          </h2>
          <p className={shared.lede}>
            Every successful project starts with understanding the brief. Let's
            start with yours.
          </p>
        </div>

        <div className={styles.formCard}>
          <p className={styles.formTitle}>Book a discovery session</p>
          <BookingForm />
        </div>
      </div>
    </section>
  );
}
