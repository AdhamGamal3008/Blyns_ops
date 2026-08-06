// §4 — Designed around how you work. Capabilities (not "modules"), each an
// alternating row with a product-screenshot slot wired in Phase E.

import {
  Contact,
  FolderKanban,
  LayoutDashboard,
  type LucideIcon,
  Package,
  SlidersHorizontal,
  Wallet,
} from "lucide-react";
import shared from "../LandingPage.module.css";
import { ScreenFrame } from "../showcase/ScreenFrame";
import { SCREENS } from "../showcase/screens";
import styles from "./Platform.module.css";

const CAPABILITIES: ReadonlyArray<{
  num: string;
  icon: LucideIcon;
  name: string;
  body: string;
  slug: string;
  shot: string;
}> = [
  { num: "01", icon: FolderKanban, name: "Projects", body: "Every phase. Every approval. Every deadline — tracked from opportunity to handover.", slug: "projects", shot: "Projects board" },
  { num: "02", icon: SlidersHorizontal, name: "Operations", body: "Daily work simplified through intelligent workflows built around your teams.", slug: "operations", shot: "Operations view" },
  { num: "03", icon: Contact, name: "Clients", body: "Relationships, quotations and communication connected together in one place.", slug: "clients", shot: "Client record" },
  { num: "04", icon: Package, name: "Inventory", body: "Know what is available, reserved, ordered or arriving — at a glance.", slug: "inventory", shot: "Inventory ledger" },
  { num: "05", icon: Wallet, name: "Finance", body: "Budgets. Invoices. Costs. Profitability — connected to the work that drives them.", slug: "finance", shot: "Finance dashboard" },
  { num: "06", icon: LayoutDashboard, name: "Leadership", body: "Dashboards that answer questions before they're asked.", slug: "leadership", shot: "Leadership dashboard" },
];

export function Platform() {
  return (
    <section
      id="platform"
      className={`${shared.section} ${shared.sectionAlt}`}
      aria-labelledby="platform-h"
    >
      <div className={shared.container}>
        <p className={shared.eyebrow}>The platform</p>
        <h2 id="platform-h" className={shared.headline}>
          Designed around how you work.
        </h2>
        <p className={shared.lede}>
          Not a stack of modules — a set of capabilities, each shaped to the way
          your operation actually runs.
        </p>

        <div className={styles.rows}>
          {CAPABILITIES.map(({ num, icon: Icon, name, body, slug, shot }) => (
            <article key={num} className={styles.row}>
              <div className={styles.copy}>
                <span className={styles.kicker}>
                  <span className={styles.icon} aria-hidden="true">
                    <Icon size={20} strokeWidth={1.5} />
                  </span>
                  <span className={styles.num}>{num}</span>
                </span>
                <h3 className={styles.name}>{name}</h3>
                <p className={styles.body}>{body}</p>
              </div>

              {/* Live, scaled product mock — reads as a screenshot, no capture. */}
              <ScreenFrame label={shot}>{SCREENS[slug]}</ScreenFrame>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
