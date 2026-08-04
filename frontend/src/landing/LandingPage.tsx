// Public landing page — its own surface, no portal shell, no auth. Composes the
// marketing sections in content order; the booking form (#book) is mounted in
// Phase D. Order and copy follow docs/LANDING_PAGE.md §3.

import { LandingFooter } from "./components/LandingFooter";
import { LandingNav } from "./components/LandingNav";
import styles from "./LandingPage.module.css";
import { Approach } from "./sections/Approach";
import { Configurable } from "./sections/Configurable";
import { Faq } from "./sections/Faq";
import { FinalCta } from "./sections/FinalCta";
import { Growth } from "./sections/Growth";
import { Hero } from "./sections/Hero";
import { Industries } from "./sections/Industries";
import { Lifecycle } from "./sections/Lifecycle";
import { Partner } from "./sections/Partner";
import { Platform } from "./sections/Platform";
import { Process } from "./sections/Process";
import { Rules } from "./sections/Rules";
import { Security } from "./sections/Security";

export function LandingPage() {
  return (
    <div className={styles.page}>
      <LandingNav />

      <main>
        <Hero />
        <Approach />
        <Industries />
        <Platform />
        <Configurable />
        <Rules />
        <Lifecycle />
        <Growth />
        <Security />
        <Partner />
        <Process />
        <Faq />
        <FinalCta />
      </main>

      <LandingFooter />
    </div>
  );
}
