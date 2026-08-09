// Hero — the first impression. An oversized serif statement whose lines mask-
// reveal after the preloader wipes, with a rust italic accent, the three tenets,
// dual pill CTAs, and a self-contained blueprint motif standing in for the
// §2 "Blueprint → Workflow → Platform" idea. Copy is verbatim from the brief.
// `ready` flips true when the preloader is done, so the intro plays on cue.

import { motion, useReducedMotion } from "framer-motion";
import { EASE } from "../motion/variants";
import { PillLink } from "../ui/PillLink";
import styles from "./Hero.module.css";

type Seg = { t: string; accent?: boolean };
const LINES: ReadonlyArray<ReadonlyArray<Seg>> = [
  [{ t: "Your Company Was" }],
  [{ t: "Built " }, { t: "Differently.", accent: true }],
  [{ t: "Your Software" }],
  [{ t: "Should Be " }, { t: "Too.", accent: true }],
];

const STAGES = ["Blueprint", "Workflow", "Platform"] as const;

export function Hero({ ready }: { ready: boolean }) {
  const reduce = useReducedMotion();
  const show = reduce || ready;

  const fade = (delay: number) => ({
    initial: reduce ? false : { opacity: 0, y: 20 },
    animate: show ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 },
    transition: { duration: 0.8, ease: EASE, delay: reduce ? 0 : delay },
  });

  return (
    <section id="top" className={styles.hero}>
      <div className={styles.bg} aria-hidden="true">
        <div className={styles.gridLines} />
        <div className={styles.glow} />
        <div className={styles.grain} />
      </div>

      <div className={`l-container ${styles.inner}`}>
        <div className={styles.copy}>
          <motion.p className={styles.eyebrow} {...fade(0)}>
            <span className={styles.eyebrowDot} aria-hidden="true" />
            Blyns · Your company&rsquo;s operating system
          </motion.p>

          <h1 className={styles.headline}>
            {LINES.map((line, i) => (
              <span className={styles.lineMask} key={i}>
                <motion.span
                  className={styles.lineInner}
                  initial={reduce ? false : { y: "110%" }}
                  animate={show ? { y: "0%" } : { y: "110%" }}
                  transition={{ duration: 0.9, ease: EASE, delay: reduce ? 0 : 0.12 + i * 0.08 }}
                >
                  {line.map((seg, j) =>
                    seg.accent ? (
                      <em className={styles.accent} key={j}>
                        {seg.t}
                      </em>
                    ) : (
                      <span key={j}>{seg.t}</span>
                    ),
                  )}
                </motion.span>
              </span>
            ))}
          </h1>

          <motion.p className={styles.support} {...fade(0.5)}>
            Most software asks your team to change how they work. We do the
            opposite. We study your operations, approvals, teams, and projects —
            then build a management platform around the way your company actually
            runs.
          </motion.p>

          <motion.ul className={styles.tenets} aria-label="Our principles" {...fade(0.6)}>
            <li>No templates.</li>
            <li>No unnecessary features.</li>
            <li>No compromises.</li>
          </motion.ul>

          <motion.div className={styles.actions} {...fade(0.7)}>
            <PillLink href="#book" variant="primary">
              Book Your Discovery Session
            </PillLink>
            <PillLink href="#platform" variant="ghost">
              See How It Works
            </PillLink>
          </motion.div>
        </div>

        <motion.div className={styles.visual} aria-hidden="true" {...fade(0.4)}>
          <HeroBlueprint active={show} reduce={!!reduce} />
        </motion.div>
      </div>

      <motion.div className={`l-container ${styles.foot}`} {...fade(0.9)}>
        <a href="#approach" className={styles.scroll}>
          <span className={styles.scrollTick} aria-hidden="true" />
          Scroll to explore
        </a>
        <span className={styles.coords}>Built around how you actually work</span>
      </motion.div>
    </section>
  );
}

/** Self-contained blueprint diagram — a drawn circle, the three-stage flow, and
    crop marks. No image; strokes draw in when `active`. */
function HeroBlueprint({ active, reduce }: { active: boolean; reduce: boolean }) {
  const draw = (delay: number) => ({
    initial: reduce ? false : { pathLength: 0, opacity: 0 },
    animate: active ? { pathLength: 1, opacity: 1 } : { pathLength: 0, opacity: 0 },
    transition: { duration: 1.3, ease: EASE, delay: reduce ? 0 : delay },
  });

  return (
    <div className={styles.blueprint}>
      <svg viewBox="0 0 480 600" className={styles.bpSvg} fill="none" role="presentation">
        {/* corner crop marks */}
        <path className={styles.bpMark} d="M24 40V16h24M456 40V16h-24M24 560v24h24M456 560v24h-24" />

        {/* decorative aperture */}
        <motion.circle className={styles.bpCircle} cx="300" cy="300" r="150" {...draw(0.2)} />
        <motion.circle className={styles.bpCircleInner} cx="300" cy="300" r="92" {...draw(0.35)} />

        {/* vertical flow axis */}
        <motion.line className={styles.bpAxis} x1="140" y1="160" x2="140" y2="440" {...draw(0.3)} />

        {STAGES.map((label, i) => {
          const y = 160 + i * 140;
          const last = i === STAGES.length - 1;
          return (
            <g key={label}>
              <motion.circle
                className={last ? styles.bpNodeActive : styles.bpNode}
                cx="140"
                cy={y}
                r="7"
                {...draw(0.5 + i * 0.12)}
              />
              <text className={styles.bpIndex} x="172" y={y - 10}>
                0{i + 1}
              </text>
              <text className={styles.bpLabel} x="172" y={y + 6}>
                {label.toUpperCase()}
              </text>
            </g>
          );
        })}

        <text className={styles.bpCaption} x="24" y="596">
          FIG.01 — BLUEPRINT TO PLATFORM
        </text>
      </svg>
    </div>
  );
}
