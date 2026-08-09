// Platform — "Designed around how you work." Six capabilities as alternating
// editorial rows, each paired with a real, live product screen (reused from the
// showcase, framed to glow on the dark canvas). Copy verbatim.

import {
  Contact,
  FolderKanban,
  LayoutDashboard,
  type LucideIcon,
  Package,
  SlidersHorizontal,
  Wallet,
} from "lucide-react";
import { Reveal } from "../motion";
import { ScreenFrame } from "../showcase/ScreenFrame";
import { SCREENS } from "../showcase/screens";
import { Heading, Section, SectionLabel } from "../ui";
import styles from "./Platform.module.css";

type Cap = { num: string; icon: LucideIcon; name: string; body: string; slug: string; shot: string };
const CAPABILITIES: ReadonlyArray<Cap> = [
  { num: "01", icon: FolderKanban, name: "Projects", body: "Every phase. Every approval. Every deadline — tracked from opportunity to handover.", slug: "projects", shot: "Projects board" },
  { num: "02", icon: SlidersHorizontal, name: "Operations", body: "Daily work simplified through intelligent workflows built around your teams.", slug: "operations", shot: "Operations view" },
  { num: "03", icon: Contact, name: "Clients", body: "Relationships, quotations and communication connected together in one place.", slug: "clients", shot: "Client record" },
  { num: "04", icon: Package, name: "Inventory", body: "Know what is available, reserved, ordered or arriving — at a glance.", slug: "inventory", shot: "Inventory ledger" },
  { num: "05", icon: Wallet, name: "Finance", body: "Budgets. Invoices. Costs. Profitability — connected to the work that drives them.", slug: "finance", shot: "Finance dashboard" },
  { num: "06", icon: LayoutDashboard, name: "Leadership", body: "Dashboards that answer questions before they're asked.", slug: "leadership", shot: "Leadership dashboard" },
];

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

              <div className={styles.screen}>
                <ScreenFrame label={shot}>{SCREENS[slug]}</ScreenFrame>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </Section>
  );
}
