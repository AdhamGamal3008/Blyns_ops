// Platform — "Designed around how you work." Six capabilities as alternating
// editorial rows, each paired with a real, live product screen (reused from the
// showcase, framed to glow on the dark canvas). The screens are code-split and
// mounted only when their row nears the viewport, keeping Recharts off first
// paint. Copy verbatim.

import { useInView } from "framer-motion";
import {
  Contact,
  FolderKanban,
  LayoutDashboard,
  type LucideIcon,
  Package,
  SlidersHorizontal,
  Wallet,
} from "lucide-react";
import { lazy, Suspense, useRef } from "react";
import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
import styles from "./Platform.module.css";

const PlatformScreen = lazy(() => import("../showcase/PlatformScreen"));

type Cap = { num: string; icon: LucideIcon; name: string; body: string; slug: string; shot: string };
const CAPABILITIES: ReadonlyArray<Cap> = [
  { num: "01", icon: FolderKanban, name: "Projects", body: "Every phase. Every approval. Every deadline — tracked from opportunity to handover.", slug: "projects", shot: "Projects board" },
  { num: "02", icon: SlidersHorizontal, name: "Operations", body: "Daily work simplified through intelligent workflows built around your teams.", slug: "operations", shot: "Operations view" },
  { num: "03", icon: Contact, name: "Clients", body: "Relationships, quotations and communication connected together in one place.", slug: "clients", shot: "Client record" },
  { num: "04", icon: Package, name: "Inventory", body: "Know what is available, reserved, ordered or arriving — at a glance.", slug: "inventory", shot: "Inventory ledger" },
  { num: "05", icon: Wallet, name: "Finance", body: "Budgets. Invoices. Costs. Profitability — connected to the work that drives them.", slug: "finance", shot: "Finance dashboard" },
  { num: "06", icon: LayoutDashboard, name: "Leadership", body: "Dashboards that answer questions before they're asked.", slug: "leadership", shot: "Leadership dashboard" },
];

/** Renders the framed product screen once its row nears the viewport; a matched
    placeholder holds the space so nothing shifts when the chunk resolves. */
function ScreenMount({ slug, label }: { slug: string; label: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "400px 0px" });
  return (
    <div ref={ref} className={styles.screen}>
      {inView ? (
        <Suspense fallback={<div className={styles.placeholder} />}>
          <PlatformScreen slug={slug} label={label} />
        </Suspense>
      ) : (
        <div className={styles.placeholder} />
      )}
    </div>
  );
}

export function Platform() {
  return (
    <Section id="platform" tone="base" labelledBy="platform-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="03">The platform</SectionLabel>
          <Heading id="platform-h">Designed around how you work.</Heading>
          <p className={styles.lede}>
            Not a stack of modules — a set of capabilities, each shaped to the way your operation
            actually runs.
          </p>
        </Reveal>

        <div className={styles.rows}>
          {CAPABILITIES.map(({ num, icon: Icon, name, body, slug, shot }) => (
            <Reveal as="article" key={num} className={styles.row} y={40}>
              <div className={styles.copy}>
                <span className={styles.kicker}>
                  <span className={styles.icon}>
                    <Icon size={20} strokeWidth={1.5} />
                  </span>
                  <span className={styles.num}>{num}</span>
                </span>
                <h3 className={styles.name}>{name}</h3>
                <p className={styles.body}>{body}</p>
              </div>

              <ScreenMount slug={slug} label={shot} />
            </Reveal>
          ))}
        </div>
      </div>
    </Section>
  );
}
