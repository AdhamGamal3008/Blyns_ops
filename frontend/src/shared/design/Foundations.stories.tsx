import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { readToken } from "./tokens";

// --- helpers ----------------------------------------------------------------

function useHex(token: string): string {
  const [hex, setHex] = useState("");
  useEffect(() => setHex(readToken(token)), [token]);
  return hex;
}

function Section(props: { title: string; description?: string; children: ReactNode }) {
  return (
    <section style={{ marginBottom: "var(--sp-8)" }}>
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "var(--step-3)",
          fontWeight: 600,
          letterSpacing: "var(--tracking-tight)",
          margin: 0,
        }}
      >
        {props.title}
      </h2>
      {props.description && (
        <p style={{ color: "var(--text-muted)", maxWidth: "62ch", margin: "var(--sp-2) 0 0" }}>
          {props.description}
        </p>
      )}
      <div style={{ marginTop: "var(--sp-4)" }}>{props.children}</div>
    </section>
  );
}

const mono: CSSProperties = {
  fontFamily: "var(--font-data)",
  fontVariantNumeric: "tabular-nums",
  fontSize: "var(--step--1)",
  color: "var(--text-muted)",
};

function Swatch(props: { token: string; name: string; note?: string; height?: number }) {
  const hex = useHex(props.token);
  return (
    <div style={{ width: 132 }}>
      <div
        style={{
          background: `var(${props.token})`,
          height: props.height ?? 64,
          borderRadius: "var(--r-md)",
          border: "1px solid var(--border)",
          boxShadow: "var(--shadow-sm)",
        }}
      />
      <div style={{ marginTop: "var(--sp-2)", fontSize: "var(--step--1)", fontWeight: 600 }}>
        {props.name}
      </div>
      <div style={mono}>{hex}</div>
      {props.note && (
        <div style={{ fontSize: "var(--step--1)", color: "var(--text-muted)" }}>{props.note}</div>
      )}
    </div>
  );
}

function RampStep(props: { token: string }) {
  const hex = useHex(props.token);
  const step = props.token.replace(/^--[a-z]+-?/, "");
  return (
    <div style={{ flex: 1, minWidth: 0 }} title={`var(${props.token}) = ${hex}`}>
      <div style={{ background: `var(${props.token})`, height: 56 }} />
      <div style={{ ...mono, textAlign: "center", paddingTop: "var(--sp-1)" }}>{step}</div>
    </div>
  );
}

function DurationChip(props: { token: string }) {
  const hex = useHex(props.token);
  return (
    <span
      style={{
        ...mono,
        color: "var(--text)",
        border: "1px solid var(--border)",
        borderRadius: "var(--r-pill)",
        padding: "var(--sp-1) var(--sp-3)",
      }}
    >
      {props.token.replace("--dur-", "")} · {hex}
    </span>
  );
}

function Ramp(props: { label: string; tokens: string[] }) {
  return (
    <div style={{ marginBottom: "var(--sp-4)" }}>
      <div style={{ fontSize: "var(--step--1)", fontWeight: 600, marginBottom: "var(--sp-2)" }}>
        {props.label}
      </div>
      <div
        style={{
          display: "flex",
          gap: 2,
          borderRadius: "var(--r-md)",
          overflow: "hidden",
          border: "1px solid var(--border)",
        }}
      >
        {props.tokens.map((t) => (
          <RampStep key={t} token={t} />
        ))}
      </div>
    </div>
  );
}

const row: CSSProperties = { display: "flex", flexWrap: "wrap", gap: "var(--sp-4)" };

// --- the page ---------------------------------------------------------------

function Foundations() {
  const semantics = [
    { fg: "--success", bg: "--success-bg", label: "Success" },
    { fg: "--warning", bg: "--warning-bg", label: "Warning" },
    { fg: "--danger", bg: "--danger-bg", label: "Danger" },
    { fg: "--info", bg: "--info-bg", label: "Info" },
  ];
  const typeSteps: { token: string; label: string; display?: boolean }[] = [
    { token: "--step-6", label: "Display 6 · Fraunces", display: true },
    { token: "--step-5", label: "Display 5 · Fraunces", display: true },
    { token: "--step-4", label: "Display 4 · Fraunces", display: true },
    { token: "--step-3", label: "Heading 3 · Fraunces", display: true },
    { token: "--step-2", label: "Heading 2", display: true },
    { token: "--step-1", label: "Heading 1" },
    { token: "--step-0", label: "Body · Inter" },
    { token: "--step--1", label: "Caption · Inter" },
  ];
  const spaces = ["--sp-1", "--sp-2", "--sp-3", "--sp-4", "--sp-5", "--sp-6", "--sp-7", "--sp-8"];
  const radii = ["--r-sm", "--r-md", "--r-lg", "--r-pill"];
  const shadows = ["--shadow-sm", "--shadow-md", "--shadow-lg"];
  const durations = [
    "--dur-instant",
    "--dur-fast",
    "--dur-base",
    "--dur-slow",
    "--dur-page",
  ];

  return (
    <div
      style={{
        background: "var(--surface)",
        color: "var(--text)",
        fontFamily: "var(--font-ui)",
        fontSize: "var(--step-0)",
        lineHeight: "var(--leading-normal)",
        minHeight: "100vh",
        padding: "var(--sp-7)",
      }}
    >
      <header style={{ marginBottom: "var(--sp-8)", maxWidth: "70ch" }}>
        <div
          style={{
            fontSize: "var(--step--1)",
            fontWeight: 600,
            letterSpacing: "var(--tracking-caps)",
            textTransform: "uppercase",
            color: "var(--oxblood)",
          }}
        >
          Blyns Design System
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--step-5)",
            fontWeight: 600,
            letterSpacing: "var(--tracking-tight)",
            lineHeight: "var(--leading-tight)",
            margin: "var(--sp-2) 0 var(--sp-3)",
          }}
        >
          Foundations
        </h1>
        <p style={{ color: "var(--text-muted)", margin: 0 }}>
          Paper and ink carry the surface; oxblood is authority and champagne is detailing —
          both rare by design. Every value below is a token; nothing downstream uses raw hex.
        </p>
      </header>

      <Section
        title="Base palette"
        description="The four brand colors. Warm paper canvas, near-black ink, oxblood for primary action, champagne strictly for detailing."
      >
        <div style={row}>
          <Swatch token="--paper" name="Paper" note="canvas" height={96} />
          <Swatch token="--ink" name="Ink" note="text / dark chrome" height={96} />
          <Swatch token="--oxblood" name="Oxblood" note="brand / primary" height={96} />
          <Swatch token="--champagne" name="Champagne" note="detailing only" height={96} />
        </div>
      </Section>

      <Section title="Ramps" description="Derived steps for neutrals, brand, and accent.">
        <Ramp
          label="Neutral (900 → 50)"
          tokens={["--n-900", "--n-800", "--n-700", "--n-600", "--n-500", "--n-400", "--n-300", "--n-200", "--n-100", "--n-50"]}
        />
        <Ramp
          label="Brand — oxblood (700 → 50)"
          tokens={["--brand-700", "--brand-600", "--brand-500", "--brand-400", "--brand-300", "--brand-50"]}
        />
        <Ramp
          label="Accent — champagne (700 → 50)"
          tokens={["--gold-700", "--gold-600", "--gold-500", "--gold-400", "--gold-300", "--gold-50"]}
        />
      </Section>

      <Section
        title="Semantic"
        description="Foregrounds tuned to clear WCAG AA (≥ 4.5:1) as badge text on their tint and as solid fills with paper text."
      >
        <div style={row}>
          {semantics.map((s) => (
            <div key={s.label} style={{ width: 200 }}>
              <div
                style={{
                  background: `var(${s.bg})`,
                  color: `var(${s.fg})`,
                  borderRadius: "var(--r-md)",
                  padding: "var(--sp-3) var(--sp-4)",
                  fontWeight: 600,
                }}
              >
                {s.label} badge
              </div>
              <div
                style={{
                  background: `var(${s.fg})`,
                  color: "var(--text-on-brand)",
                  borderRadius: "var(--r-md)",
                  padding: "var(--sp-2) var(--sp-4)",
                  marginTop: "var(--sp-2)",
                  fontWeight: 600,
                }}
              >
                Solid fill
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Surfaces" description="Named by role, not by color.">
        <div style={row}>
          <Swatch token="--surface" name="Surface" note="paper canvas" />
          <Swatch token="--surface-raised" name="Raised" note="cards / modals" />
          <Swatch token="--surface-sunken" name="Sunken" note="zebra / wells" />
          <Swatch token="--surface-inverse" name="Inverse" note="sidebar / command bar" />
        </div>
      </Section>

      <Section
        title="Typography"
        description="Fraunces for display, Inter for UI and data. Numerals are tabular so columns align."
      >
        {typeSteps.map((t) => (
          <div
            key={t.token}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: "var(--sp-4)",
              padding: "var(--sp-2) 0",
              borderBottom: "1px solid var(--border)",
            }}
          >
            <span style={{ ...mono, width: 180, flexShrink: 0 }}>{t.label}</span>
            <span
              style={{
                fontFamily: t.display ? "var(--font-display)" : "var(--font-ui)",
                fontSize: `var(${t.token})`,
                fontWeight: t.display ? 600 : 400,
                letterSpacing: t.display ? "var(--tracking-tight)" : undefined,
                lineHeight: "var(--leading-tight)",
              }}
            >
              Reveal &amp; grain 1,240
            </span>
          </div>
        ))}
      </Section>

      <Section title="Space" description="4-based scale.">
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
          {spaces.map((s) => (
            <div key={s} style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)" }}>
              <span style={{ ...mono, width: 64 }}>{s.replace("--", "")}</span>
              <div style={{ height: 16, width: `var(${s})`, background: "var(--oxblood)", borderRadius: "var(--r-sm)" }} />
            </div>
          ))}
        </div>
      </Section>

      <Section title="Radius & elevation">
        <div style={{ ...row, alignItems: "flex-end", marginBottom: "var(--sp-5)" }}>
          {radii.map((r) => (
            <div key={r} style={{ textAlign: "center" }}>
              <div
                style={{
                  width: 72,
                  height: 72,
                  background: "var(--surface-raised)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: `var(${r})`,
                }}
              />
              <div style={{ ...mono, marginTop: "var(--sp-1)" }}>{r.replace("--", "")}</div>
            </div>
          ))}
        </div>
        <div style={row}>
          {shadows.map((sh) => (
            <div key={sh} style={{ textAlign: "center" }}>
              <div
                style={{
                  width: 120,
                  height: 72,
                  background: "var(--surface-raised)",
                  borderRadius: "var(--r-md)",
                  boxShadow: `var(${sh})`,
                }}
              />
              <div style={{ ...mono, marginTop: "var(--sp-2)" }}>{sh.replace("--", "")}</div>
            </div>
          ))}
        </div>
      </Section>

      <Section
        title="Motion & focus"
        description="Durations pair with --ease-out / --ease-inout. Reduced-motion collapses every transition. The focus ring is champagne over a gold-700 edge so it clears 3:1 on paper."
      >
        <div style={{ ...row, marginBottom: "var(--sp-5)" }}>
          {durations.map((d) => (
            <DurationChip key={d} token={d} />
          ))}
        </div>
        <button
          type="button"
          style={{
            fontFamily: "var(--font-ui)",
            fontSize: "var(--step-0)",
            fontWeight: 600,
            color: "var(--text-on-brand)",
            background: "var(--oxblood)",
            border: "none",
            borderRadius: "var(--r-md)",
            padding: "var(--sp-3) var(--sp-5)",
            outline: "2px solid var(--focus-ring)",
            outlineOffset: 2,
            boxShadow: "0 0 0 4px var(--focus-ring-edge)",
            cursor: "pointer",
          }}
        >
          Focus ring preview
        </button>
      </Section>
    </div>
  );
}

const meta: Meta<typeof Foundations> = {
  title: "Design/Foundations",
  component: Foundations,
};

export default meta;

export const Page: StoryObj<typeof Foundations> = {};
