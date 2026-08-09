// FAQ — "Questions we usually hear." A native <details> accordion (accessible,
// keyboard-friendly), numbered, with a chevron that turns on open. Copy verbatim.

import { ChevronDown } from "lucide-react";
import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
import styles from "./Faq.module.css";

const QA: ReadonlyArray<[string, string]> = [
  [
    "Why not just use an off-the-shelf ERP?",
    "Off-the-shelf systems ask you to reshape your business around their assumptions. We do the reverse — we study how your company already works and build the platform around it, so adoption feels natural rather than forced.",
  ],
  [
    "Can we keep our existing workflows?",
    "Yes. Your approvals, stages, and responsibilities are the starting point, not something we override. We map them precisely and encode them as they already are.",
  ],
  [
    "Can approvals be customized?",
    "Completely. Single sign-off or multi-level chains, with different rules per department or project type — approvals are configured to match how decisions are actually made in your company.",
  ],
  [
    "Can different departments have different dashboards?",
    "Yes. Procurement, production, finance, and leadership each get a view built around the questions they need answered — not one generic screen for everyone.",
  ],
  [
    "Can we integrate with existing software?",
    "Where it adds value, yes. The platform is designed to connect with the tools you rely on, so information flows instead of being re-entered by hand.",
  ],
  [
    "Can multiple branches use the same platform?",
    "Yes. Multiple branches — or multiple companies — run under one platform, each with its own data, users, and rules, kept fully isolated from one another.",
  ],
  [
    "How long does implementation take?",
    "Because we map before we build, timelines are predictable. Smaller deployments take weeks; larger, multi-department rollouts are phased so you see value early and grow into the rest.",
  ],
];

export function Faq() {
  return (
    <Section id="faq" tone="base" labelledBy="faq-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="11">FAQ</SectionLabel>
          <Heading id="faq-h">Questions we usually hear.</Heading>
        </Reveal>

        <div className={styles.list}>
          {QA.map(([q, a], i) => (
            <details key={q} className={styles.item}>
              <summary className={styles.q}>
                <span className={styles.qIndex}>0{i + 1}</span>
                <span className={styles.qText}>{q}</span>
                <ChevronDown className={styles.chev} size={20} aria-hidden="true" />
              </summary>
              <div className={styles.a}>
                <p>{a}</p>
              </div>
            </details>
          ))}
        </div>
      </div>
    </Section>
  );
}
