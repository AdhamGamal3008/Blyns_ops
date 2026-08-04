// §9 — Security designed into every layer. Dark icon grid. Each item maps to a
// capability the platform genuinely ships (RBAC, IP/country controls, rate
// limiting, audit history, multi-tenant isolation).

import { Gauge, Globe, History, KeyRound, Layers, Lock, type LucideIcon, Server } from "lucide-react";
import shared from "../LandingPage.module.css";
import styles from "./Security.module.css";

const LAYERS: ReadonlyArray<[LucideIcon, string]> = [
  [Server, "Enterprise-grade infrastructure"],
  [KeyRound, "Role-based permissions"],
  [Globe, "IP and country access controls"],
  [Gauge, "Rate limiting"],
  [History, "Audit history"],
  [Layers, "Secure multi-tenant architecture"],
  [Lock, "Encrypted communication"],
];

export function Security() {
  return (
    <section
      id="security"
      className={`${shared.section} ${shared.sectionInk}`}
      aria-labelledby="security-h"
    >
      <div className={shared.container}>
        <p className={`${shared.eyebrow} ${shared.eyebrowInk}`}>Security</p>
        <h2 id="security-h" className={`${shared.headline} ${shared.headlineInk}`}>
          Security designed into every layer.
        </h2>

        <ul className={styles.grid}>
          {LAYERS.map(([Icon, label]) => (
            <li key={label} className={styles.item}>
              <span className={styles.icon} aria-hidden="true">
                <Icon size={22} strokeWidth={1.5} />
              </span>
              <span className={styles.label}>{label}</span>
            </li>
          ))}
        </ul>

        <p className={`${shared.lede} ${shared.ledeInk} ${styles.close}`}>
          Because your operational data deserves the same level of protection as
          your financial data.
        </p>
      </div>
    </section>
  );
}
