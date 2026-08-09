// Public landing page — its own surface, no portal shell, no auth. The redesign
// gives the landing its own dark, editorial visual language (see ./theme). This
// composition currently mounts the new chrome + hero (Phase 1); the remaining
// sections are rebuilt in the new language in later phases and re-added here.

import { useState } from "react";
import { LandingNav } from "./chrome/LandingNav";
import { PRELOAD_KEY, Preloader } from "./chrome/Preloader";
import { Hero } from "./sections/Hero";
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
      </main>
    </div>
  );
}
