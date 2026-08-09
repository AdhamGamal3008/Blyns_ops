// Public landing page — its own surface, no portal shell, no auth. The redesign
// gives the landing its own dark, editorial visual language (see ./theme). This
// composition mounts the new chrome + hero (Phase 1), the editorial sections
// (Phase 2), and the structured sections (Phase 3). The booking CTA + footer are
// rebuilt in the new language in Phase 4.

import { useState } from "react";
import { LandingFooter } from "./chrome/LandingFooter";
import { LandingNav } from "./chrome/LandingNav";
import { PRELOAD_KEY, Preloader } from "./chrome/Preloader";
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
import "./theme/theme.css";

export function LandingPage() {
  const [ready, setReady] = useState(
    () => typeof window !== "undefined" && window.sessionStorage.getItem(PRELOAD_KEY) === "1",
  );

  return (
    <div data-surface="landing">
      <Preloader onDone={() => setReady(true)} />
      <LandingNav />
      <main>
        <Hero ready={ready} />
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
