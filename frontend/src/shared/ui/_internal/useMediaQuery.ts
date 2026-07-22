// Layout decisions a media query cannot express — e.g. rendering a *different
// component* below a breakpoint rather than restyling the same one.
//
// Prefer plain CSS wherever restyling is enough; reach for this only when the
// two states are genuinely different markup.

import { useEffect, useState } from "react";

function match(query: string): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(query).matches;
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => match(query));

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    mq.addEventListener("change", onChange);
    setMatches(mq.matches);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** The shell's phone breakpoint, shared so components agree on where it is. */
export const PHONE_QUERY = "(max-width: 767px)";

export function useIsPhone(): boolean {
  return useMediaQuery(PHONE_QUERY);
}
