// Shared building blocks for the per-module Analytics/Overview tabs
// (docs/PROJECT_ANALYTICS_PLAN.md). Charts reuse the shared/ui/Chart primitives;
// these add the brand palette, number formatters, a static legend (identity is
// label + swatch, never colour alone), and a titled chart card.

import type { ReactNode } from "react";
import { Card, CardHeader } from "../../shared/ui";
import styles from "./parts.module.css";
import { companyCurrency } from "../../shared/currency";

// Brand chart palette (see shared/ui/Chart): oxblood leads, gold highlights,
// info/success round it out. Assigned to entities in a fixed order, never cycled.
export const INK = "var(--oxblood)";
export const GOLD = "var(--gold-600)";
export const INFO = "var(--info)";
export const GOOD = "var(--success)";

export const int = (n: number) => n.toLocaleString();
export const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

export const money = (n: number, _currency?: string) =>
  n.toLocaleString(undefined, {
    style: "currency", currency: companyCurrency(), maximumFractionDigits: 0,
  });

/** Compact currency for chart axes in the company currency ("$1.2K", "EGP 1.2K").
 *  notation:"compact" supplies both the symbol and the k/M suffix, so no currency
 *  symbol is ever hardcoded. */
export const moneyShort = (n: number) =>
  new Intl.NumberFormat(undefined, {
    style: "currency", currency: companyCurrency(),
    notation: "compact", maximumFractionDigits: 1,
  }).format(n);

// Chart data is a bag of keyed numbers/strings; our typed rows satisfy that shape.
export type Rows = Array<Record<string, string | number>>;
export const rows = (x: readonly object[]) => x as unknown as Rows;

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className={styles.legend}>
      {items.map((it) => (
        <li key={it.label}>
          <span className={styles.swatch} style={{ background: it.color }} aria-hidden="true" />
          {it.label}
        </li>
      ))}
    </ul>
  );
}

export function ChartCard(props: {
  title: string;
  description?: string;
  legend?: { label: string; color: string }[];
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader title={props.title} description={props.description} />
      {props.legend && <Legend items={props.legend} />}
      {props.children}
    </Card>
  );
}
