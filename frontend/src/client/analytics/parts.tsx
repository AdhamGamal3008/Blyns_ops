// Shared building blocks for the per-module Analytics/Overview tabs
// (docs/PROJECT_ANALYTICS_PLAN.md). Charts reuse the shared/ui/Chart primitives;
// these add the brand palette, number formatters, a static legend (identity is
// label + swatch, never colour alone), and a titled chart card.

import type { ReactNode } from "react";
import { Card, CardHeader } from "../../shared/ui";
import styles from "./parts.module.css";

// Brand chart palette (see shared/ui/Chart): oxblood leads, gold highlights,
// info/success round it out. Assigned to entities in a fixed order, never cycled.
export const INK = "var(--oxblood)";
export const GOLD = "var(--gold-600)";
export const INFO = "var(--info)";
export const GOOD = "var(--success)";

export const int = (n: number) => n.toLocaleString();
export const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);

export const money = (n: number, currency = "USD") =>
  n.toLocaleString(undefined, { style: "currency", currency, maximumFractionDigits: 0 });

/** Compact currency for chart axes ($1.2k); full money() for tiles/tooltips. */
export const moneyShort = (n: number) =>
  Math.abs(n) >= 1000 ? `$${(n / 1000).toFixed(Math.abs(n) % 1000 ? 1 : 0)}k` : `$${Math.round(n)}`;

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
