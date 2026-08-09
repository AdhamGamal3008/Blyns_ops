// LiveClock — a small ticking clock for the nav. Shows the visitor's own local
// time and city (derived from their timezone), so it reads as "we're present"
// without asserting a studio location we don't have in the content.

import { useEffect, useState } from "react";

function read() {
  const now = new Date();
  const time = now.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  let zone = "";
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone ?? "";
    zone = tz.split("/").pop()?.replace(/_/g, " ").toUpperCase() ?? "";
  } catch {
    zone = "";
  }
  return { time, zone };
}

export function LiveClock({ className }: { className?: string }) {
  const [{ time, zone }, set] = useState(read);

  useEffect(() => {
    const id = window.setInterval(() => set(read()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <span className={className}>
      {time}
      {zone ? ` — ${zone}` : ""}
    </span>
  );
}
