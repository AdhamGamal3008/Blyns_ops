// §12 — Questions we usually hear. Native <details> accordion (accessible, no JS).
// Answers authored to the positioning: craft over jargon, and honest about what
// the platform genuinely does (configurable approvals, per-team dashboards,
// isolated multi-tenant branches).

import { ChevronDown } from "lucide-react";
import shared from "../LandingPage.module.css";
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
    <section id="faq" className={shared.section} aria-labelledby="faq-h">
      <div className={shared.container}>
        <p className={shared.eyebrow}>FAQ</p>
        <h2 id="faq-h" className={shared.headline}>
          Questions we usually hear.
        </h2>

        <div className={styles.list}>
          {QA.map(([q, a]) => (
            <details key={q} className={styles.item}>
              <summary className={styles.q}>
                <span>{q}</span>
                <ChevronDown className={styles.chevron} size={22} aria-hidden="true" />
              </summary>
              <p className={styles.a}>{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
