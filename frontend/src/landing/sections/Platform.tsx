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
import styles from "./Platform.module.css";

const CAPABILITIES: ReadonlyArray<{
  num: string;
  icon: LucideIcon;
  name: string;
  body: string;
  shot: string;
}> = [
  { num: "01", icon: FolderKanban, name: "Projects", body: "Every phase. Every approval. Every deadline — tracked from opportunity to handover.", shot: "Projects board" },
  { num: "02", icon: SlidersHorizontal, name: "Operations", body: "Daily work simplified through intelligent workflows built around your teams.", shot: "Operations view" },
  { num: "03", icon: Contact, name: "Clients", body: "Relationships, quotations and communication connected together in one place.", shot: "Client record" },
  { num: "04", icon: Package, name: "Inventory", body: "Know what is available, reserved, ordered or arriving — at a glance.", shot: "Inventory ledger" },
  { num: "05", icon: Wallet, name: "Finance", body: "Budgets. Invoices. Costs. Profitability — connected to the work that drives them.", shot: "Finance dashboard" },
  { num: "06", icon: LayoutDashboard, name: "Leadership", body: "Dashboards that answer questions before they're asked.", shot: "Leadership dashboard" },
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
          {CAPABILITIES.map(({ num, icon: Icon, name, body, shot }) => (
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

              {/* Screenshot slot — a product-window frame filled in Phase E. */}
              <div className={styles.shot} aria-hidden="true">
                <span className={styles.shotBar}>
                  <i /><i /><i />
                </span>
                <span className={styles.shotLabel}>{shot}</span>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
