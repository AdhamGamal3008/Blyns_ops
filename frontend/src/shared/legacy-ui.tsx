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
