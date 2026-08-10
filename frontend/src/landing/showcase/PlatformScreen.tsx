// Lazy chunk boundary for the Platform product screens. Importing this module
// pulls in the full showcase (MockShell + SCREENS + Recharts); it is code-split
// via React.lazy and only loaded when a Platform row nears the viewport, so none
// of that weight lands on the landing's first paint. Default export for lazy().

import { ScreenFrame } from "./ScreenFrame";
import { SCREENS } from "./screens";

export default function PlatformScreen({ slug, label }: { slug: string; label: string }) {
  return <ScreenFrame label={label}>{SCREENS[slug]}</ScreenFrame>;
}
