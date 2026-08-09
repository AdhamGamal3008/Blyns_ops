// Industries — "Every company is different." A gallery of the five trades Blyns
// is built for, as numbered cards that light up on hover. Copy verbatim.

import { Blocks, Building2, Handshake, Layers, type LucideIcon, Package } from "lucide-react";
import { Reveal } from "../motion";
import { Heading, Section, SectionLabel } from "../ui";
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
    <Section id="industries" tone="raised" labelledBy="industries-h">
      <div className="l-container">
        <Reveal className={styles.head}>
          <SectionLabel index="02">Who it&rsquo;s for</SectionLabel>
          <Heading id="industries-h" sub="So every platform is different.">
            Every company is different.
          </Heading>
        </Reveal>

        <ul className={styles.grid}>
          {INDUSTRIES.map(([Icon, title, body], i) => (
            <Reveal as="li" key={title} className={styles.card} delay={i * 0.06}>
              <span className={styles.num}>0{i + 1}</span>
              <span className={styles.icon}>
                <Icon size={24} strokeWidth={1.4} />
              </span>
              <h3 className={styles.cardTitle}>{title}</h3>
              <p className={styles.cardBody}>{body}</p>
            </Reveal>
          ))}
        </ul>
      </div>
    </Section>
  );
}
