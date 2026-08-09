// Public landing page — its own surface, no portal shell, no auth. The redesign
// gives the landing its own dark, editorial visual language (see ./theme). This
// composition mounts the new chrome + hero (Phase 1) and the editorial sections
// (Phase 2); the structured sections (Industries, Platform, Lifecycle, Security,
// Process, FAQ) and the booking CTA are rebuilt in the new language in Phases 3–4.

import { useState } from "react";
import { LandingNav } from "./chrome/LandingNav";
import { PRELOAD_KEY, Preloader } from "./chrome/Preloader";
import { Approach } from "./sections/Approach";
import { Configurable } from "./sections/Configurable";
import { Growth } from "./sections/Growth";
import { Hero } from "./sections/Hero";
import { Partner } from "./sections/Partner";
import { Rules } from "./sections/Rules";
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
        <Configurable />
        <Rules />
        <Growth />
        <Partner />
      </main>
    </div>
  );
}
