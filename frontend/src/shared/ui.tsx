// Minimal UI kit — plain CSS classes from styles.css, no component library.

import type { ReactNode } from "react";

export function Card(props: {
  title?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${props.className ?? ""}`}>
      {(props.title || props.actions) && (
        <header className="card-head">
          {props.title && <h3>{props.title}</h3>}
          {props.actions && <div className="card-actions">{props.actions}</div>}
        </header>
      )}
      {props.children}
    </section>
  );
}

export function Button(props: {
  children: ReactNode;
  onClick?: () => void;
  type?: "button" | "submit";
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type={props.type ?? "button"}
      className={`btn btn-${props.variant ?? "primary"}`}
      onClick={props.onClick}
      disabled={props.disabled}
      title={props.title}
    >
      {props.children}
    </button>
  );
}

export function Field(props: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span className="field-label">{props.label}</span>
      {props.children}
    </label>
  );
}

export function Badge(props: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${props.tone ?? "neutral"}`}>{props.children}</span>;
}

export function Spinner() {
  return <div className="spinner" role="status" aria-label="loading" />;
}

export function ErrorNote(props: { error: unknown }) {
  if (!props.error) return null;
  const message =
    props.error instanceof Error ? props.error.message : String(props.error);
  return <div className="error-note">{message}</div>;
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function formatBytes(n: number): string {
  if (n >= 1 << 30) return `${(n / (1 << 30)).toFixed(1)} GB`;
  if (n >= 1 << 20) return `${(n / (1 << 20)).toFixed(1)} MB`;
  if (n >= 1 << 10) return `${(n / (1 << 10)).toFixed(1)} KB`;
  return `${n} B`;
}
