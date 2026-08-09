// Security — "Security designed into every layer." A dark icon grid that maps to
// controls the platform genuinely ships (RBAC, IP/country rules, rate limiting,
// audit history, tenant isolation). Copy verbatim.

import { Gauge, Globe, History, KeyRound, Layers, Lock, type LucideIcon, Server } from "lucide-react";
import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
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
    <Section id="security" tone="deep" labelledBy="security-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="08">Security</SectionLabel>
          <Heading id="security-h">Security designed into every layer.</Heading>
        </Reveal>

        <ul className={styles.grid}>
          {LAYERS.map(([Icon, label], i) => (
            <Reveal as="li" key={label} className={styles.item} delay={i * 0.05}>
              <span className={styles.icon}>
                <Icon size={22} strokeWidth={1.4} />
              </span>
              <span className={styles.label}>{label}</span>
            </Reveal>
          ))}
        </ul>

        <Reveal>
          <p className={styles.close}>
            Because your operational data deserves the same level of protection as your financial
            data.
          </p>
        </Reveal>
      </div>
    </Section>
  );
}
