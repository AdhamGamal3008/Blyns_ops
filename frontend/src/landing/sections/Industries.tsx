// §3 — Every company is different, so every platform is different. Industry cards.

import { Blocks, Building2, Handshake, Layers, type LucideIcon, Package } from "lucide-react";
import shared from "../LandingPage.module.css";
import styles from "./Industries.module.css";

const INDUSTRIES: ReadonlyArray<[LucideIcon, string, string]> = [
  [Building2, "Interior Fit-Out", "Manage drawings, approvals, procurement, installations and handovers."],
  [Layers, "Flooring Specialists", "Track projects from quotation to installation with complete material visibility."],
  [Blocks, "Wall Cladding", "Control fabrication, production scheduling and site execution from one platform."],
  [Package, "Custom Furniture", "Monitor production, workshops, deliveries and client approvals in one place."],
  [Handshake, "General Contractors", "Coordinate every department without spreadsheets or disconnected software."],
];

export function Industries() {
  return (
    <section
      id="industries"
      className={`${shared.section} ${shared.sectionSunken}`}
      aria-labelledby="industries-h"
    >
      <div className={shared.container}>
        <p className={shared.eyebrow}>Who it's for</p>
        <h2 id="industries-h" className={shared.headline}>
          Every company is different.
          <span className={shared.headlineSub}>So every platform is different.</span>
        </h2>

        <ul className={styles.grid}>
          {INDUSTRIES.map(([Icon, title, body]) => (
            <li key={title} className={styles.card}>
              <span className={styles.icon} aria-hidden="true">
                <Icon size={22} strokeWidth={1.5} />
              </span>
              <h3 className={styles.cardTitle}>{title}</h3>
              <p className={styles.cardBody}>{body}</p>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
