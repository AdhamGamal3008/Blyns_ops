// One reduced-motion signal for motion that CSS cannot switch off.
//
// tokens.css already neutralises every CSS animation and transition under
// `prefers-reduced-motion: reduce`. That covers most of the app — but not
// motion computed in JS (Recharts draws its series on a timer, Framer
// interpolates in rAF), which is what this hook is for.

import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

/** matchMedia is absent under SSR and in some test environments; treat a missing
 *  implementation as "no preference expressed" rather than throwing. */
function query(): MediaQueryList | null {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return null;
  }
  return window.matchMedia(QUERY);
}

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => query()?.matches ?? false);

  useEffect(() => {
    const mq = query();
    if (!mq) return;
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    setReduced(mq.matches);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
