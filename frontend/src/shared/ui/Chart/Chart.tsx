import {
  Area,
  AreaChart,
  Bar,
  BarChart as ReBarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
// Recharts draws its series on a JS timer, so the CSS reduced-motion kill
// switch in tokens.css cannot reach it and its 1500ms default sits well outside
// the --dur-page budget. Both are set explicitly here instead.
import { DUR, useReducedMotion } from "../../motion";
import styles from "./Chart.module.css";

// Oxblood leads; champagne gold is the highlight; info/success round out the set.
const SERIES_COLORS = [
  "var(--oxblood)",
  "var(--gold-600)",
  "var(--info)",
  "var(--success)",
];

const AXIS_TICK = { fill: "var(--text-muted)", fontSize: 12 } as const;

export interface ChartSeries {
  key: string;
  label?: string;
  color?: string;
}

export interface ChartProps {
  data: Array<Record<string, string | number>>;
  xKey: string;
  series: ChartSeries[];
  height?: number;
  formatValue?: (value: number) => string;
}

interface TooltipInnerProps {
  active?: boolean;
  label?: string | number;
  payload?: Array<{ dataKey?: string | number; name?: string; value?: number; color?: string }>;
  formatValue?: (value: number) => string;
}

function ChartTooltip({ active, label, payload, formatValue }: TooltipInnerProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <div className={styles.tooltipLabel}>{label}</div>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className={styles.tooltipRow}>
          <span className={styles.tooltipDot} style={{ background: p.color }} aria-hidden="true" />
          <span className={styles.tooltipName}>{p.name}</span>
          <span className={styles.tooltipValue}>
            {formatValue && typeof p.value === "number" ? formatValue(p.value) : p.value}
          </span>
        </div>
      ))}
    </div>
  );
}

export function TrendChart({ data, xKey, series, height = 240, formatValue }: ChartProps) {
  const reduced = useReducedMotion();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`chart-grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color ?? SERIES_COLORS[i % SERIES_COLORS.length]} stopOpacity={0.28} />
              <stop offset="100%" stopColor={s.color ?? SERIES_COLORS[i % SERIES_COLORS.length]} stopOpacity={0.02} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey={xKey} tickLine={false} axisLine={{ stroke: "var(--border)" }} tick={AXIS_TICK} />
        <YAxis tickLine={false} axisLine={false} tick={AXIS_TICK} width={48} tickFormatter={formatValue} />
        <Tooltip
          content={<ChartTooltip formatValue={formatValue} />}
          cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }}
        />
        {series.map((s, i) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label ?? s.key}
            stroke={s.color ?? SERIES_COLORS[i % SERIES_COLORS.length]}
            strokeWidth={2}
            fill={`url(#chart-grad-${s.key})`}
            isAnimationActive={!reduced}
            animationDuration={DUR.slow}
            animationEasing="ease-out"
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function BarChart({ data, xKey, series, height = 240, formatValue }: ChartProps) {
  const reduced = useReducedMotion();
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ReBarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid vertical={false} stroke="var(--border)" />
        <XAxis dataKey={xKey} tickLine={false} axisLine={{ stroke: "var(--border)" }} tick={AXIS_TICK} />
        <YAxis tickLine={false} axisLine={false} tick={AXIS_TICK} width={48} tickFormatter={formatValue} />
        <Tooltip
          content={<ChartTooltip formatValue={formatValue} />}
          cursor={{ fill: "var(--surface-sunken)" }}
        />
        {series.map((s, i) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label ?? s.key}
            fill={s.color ?? SERIES_COLORS[i % SERIES_COLORS.length]}
            radius={[4, 4, 0, 0]}
            maxBarSize={48}
            isAnimationActive={!reduced}
            animationDuration={DUR.slow}
            animationEasing="ease-out"
          />
        ))}
      </ReBarChart>
    </ResponsiveContainer>
  );
}
