// Renders a live module mock inside a browser-style frame, scaled to fit. The
// mock is laid out at a fixed desktop size (DESIGN_W×DESIGN_H) and shrunk with a
// CSS transform whose factor tracks the frame's real width (ResizeObserver), so
// it reads as a crisp product screenshot at any column width — no PNG, no capture.
//
// The scaled canvas is `inert`, so none of the mock's buttons/tables/links are
// focusable, clickable, or announced by assistive tech; the frame carries a
// single descriptive label via role="img".

import { useEffect, useRef, useState, type ReactNode } from "react";
import styles from "./ScreenFrame.module.css";

const DESIGN_W = 1160;
const DESIGN_H = 725;

export function ScreenFrame({ children, label }: { children: ReactNode; label: string }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(DESIGN_W ? 0.45 : 1);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const update = () => setScale(el.clientWidth / DESIGN_W);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <figure className={styles.frame} role="img" aria-label={`${label} — a view of the Blyns platform`}>
      <div className={styles.bar} aria-hidden="true">
        <i /><i /><i />
      </div>
      <div
        ref={viewportRef}
        className={styles.viewport}
        style={{ aspectRatio: `${DESIGN_W} / ${DESIGN_H}` }}
      >
        <div
          ref={(el) => {
            if (el) el.inert = true;
          }}
          className={styles.canvas}
          style={{ width: DESIGN_W, height: DESIGN_H, transform: `scale(${scale})` }}
        >
          {children}
        </div>
      </div>
    </figure>
  );
}
