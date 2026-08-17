# PREMIUM UI/UX INITIATIVE

**A standalone initiative — read this file first to begin it.**

This is a **new, self-contained workstream**, not a continuation of the ERP
build. It is launched fresh once the ERP is feature-complete, and its job is to
elevate the finished product to a **premium SaaS** standard across admin and
client: a coherent design system, upgraded React components, purposeful
animation, and a mobile-web experience that is beautiful, not merely functional.

Treat the finished ERP as the **subject** this initiative acts on. The build's
own rules (fully custom code / self-hosted, accessibility floor, tests with
features) still hold, but this work is planned, branched, and tracked on its own.

---

## How to run this initiative

- **Prerequisite:** the ERP build is complete and its test suite is green. Do not
  begin this work on an unfinished or unstable build.
- **This file is the entry point.** When starting the initiative, have Claude Code
  read this document first, then work its 8 phases **in order**, one phase per
  session: read the phase → propose the component/file list (and a screenshot
  where possible) → get approval → implement → visual QA → commit → **stop**.
- **Mandatory stop after every phase.** Claude Code must halt at the end of each
  phase and wait for your explicit go-ahead before starting the next one. This is
  your control point — use it to run the app yourself, run your own tests, and
  review the result. Do not batch phases, do not roll into the next phase
  automatically, even if a phase finished quickly or seems trivial. Only an
  explicit instruction from you ("continue" / "start Phase N") resumes the work.
- **Work on a dedicated branch** (e.g. `design-system`) so the visual refactor is
  isolated from the stable build until you're ready to merge.
- **Freeze the token layer (Phase 1) before styling anything.** Everything
  downstream derives from it; settling the palette steps and type scale up front
  prevents rework.

### Kickoff prompt (paste this to start the initiative)

```
This is a new initiative, separate from the ERP build. Read
docs/UI_REFACTOR.md in full.

Do NOT write code yet. Instead:
1. Confirm the build is complete and tests are green (ask me if unsure).
2. Create a `design-system` branch.
3. Summarize the design thesis and the token system in your own words.
4. Give me the Phase 1 plan (Design system foundation): the files you'll
   create under frontend/src/shared/design/, the exact palette ramp values
   and type scale you'll commit, and how you'll expose tokens to the app.

Stop after the plan and wait for my approval.
```

Then run one phase at a time: "implement Phase N, then show me the Storybook /
screenshots and the visual-QA result, and stop." After you have run it, tested
it, and reviewed it yourself, reply "continue" to release the next phase. Nothing
proceeds without that.

---

## Design thesis (ground it in the subject)

The business is **wall cladding, flooring, and customized furniture** — a
craft-and-materials world of finishes, grain, inlay, and precise reveals. The
interface should feel like the brand's showroom, not a generic dashboard.

- **Authority, not noise.** Oxblood is the voice of authority (primary actions,
  active state, brand moments). Champagne gold is *detailing* — a fine inlay line,
  a hairline divider, a focus ring — used the way metal trim is used on fine
  furniture: sparingly, precisely, never as a fill for large areas or small text.
- **Paper and ink do the work.** The warm paper canvas and near-black ink carry
  99% of the surface; the two brand colors earn their impact by being rare.
- **Signature moment:** the Project Management **16-stage stage-gate pipeline**
  rendered as a crafted, material-inspired process spine (Phase 5). Spend the
  boldness here; keep everything else quiet and disciplined.
- **Avoid the templated look.** Do **not** default to the cream + high-contrast
  Playfair serif + terracotta cluster. The paper is warmer and quieter than that
  trope, the accent is oxblood/gold not clay, and the display face is chosen for
  an architectural/crafted character (Phase 1), not editorial drama.

---

## Library stack (all open-source libraries, not external services)

The "no third-party integrations" rule targets external SaaS/APIs, not npm
packages. These are local, self-hosted libraries and are all fine:

| Need | Library | Why |
|---|---|---|
| Accessible headless primitives | **Radix UI** | correct a11y/keyboard behavior for dialogs, menus, tabs, tooltips — you style them with tokens |
| Animation | **Framer Motion** | declarative, spring-based, respects reduced-motion |
| Icons | **lucide-react** | consistent, tunable stroke icons |
| Data tables | **TanStack Table** | headless sorting/filtering/pagination for dense grids |
| Charts | **Recharts** or **visx** | dashboard/finance/inventory visuals, themeable to tokens |
| Component dev + docs | **Storybook** | build/review components in isolation |
| Visual regression | **Playwright** screenshots | catch unintended visual drift |
| Styling | **Tailwind** *or* **vanilla-extract / CSS Modules** | either works; whichever you pick consumes the token layer below |

Self-host fonts and bundle everything — nothing is fetched at runtime from third
parties.

---

## Phase 1 — Design system foundation (tokens)

Everything downstream derives from this layer. Build it once, in
`frontend/src/shared/design/`, exposed as CSS custom properties so it works with
Tailwind or CSS Modules.

### 1.1 Color tokens

Base palette (your four colors) and derived ramps. Starting values — tune the
intermediate steps against real screens.

```css
:root {
  /* Base palette */
  --paper:    #F9F8F6;   /* canvas */
  --ink:      #1C1D1F;   /* primary text / dark chrome */
  --oxblood:  #8C1D24;   /* brand / primary action */
  --champagne:#C9A054;   /* accent / detailing only */

  /* Neutral ramp (warm grays from ink -> paper) */
  --n-900:#1C1D1F; --n-800:#2A2B2E; --n-700:#3C3D40; --n-600:#55565A;
  --n-500:#6E6F73; --n-400:#8A8B8F; --n-300:#ADAEB1; --n-200:#D3D2CE;
  --n-100:#E9E8E4; --n-50:#F9F8F6;

  /* Brand (oxblood) ramp */
  --brand-700:#6E141A; --brand-600:#7D181F; --brand-500:#8C1D24;
  --brand-400:#A63640; --brand-300:#C15E66; --brand-50:#F7E9EA;

  /* Accent (champagne) ramp */
  --gold-700:#9A7735; --gold-600:#B08C44; --gold-500:#C9A054;
  --gold-400:#D6B679; --gold-300:#E3CDA1; --gold-50:#F7EFDD;

  /* Semantic — harmonized, but distinct from brand oxblood */
  --success:#3E7C5A; --success-bg:#E7F0EB;
  --warning:#B4791F; --warning-bg:#F6ECD8;   /* ochre, NOT the gold accent */
  --danger:#C0392B;  --danger-bg:#F7E6E4;    /* brighter/warmer than oxblood */
  --info:#3E5C76;    --info-bg:#E7EDF2;

  /* Surface roles */
  --surface:        var(--paper);
  --surface-raised: #FFFFFF;
  --surface-sunken: #F1EFEA;
  --surface-inverse:var(--ink);      /* dark chrome: sidebars, command bar */
  --border:         var(--n-200);
  --border-strong:  var(--n-300);
  --text:           var(--n-800);
  --text-muted:     var(--n-500);
  --text-on-brand:  var(--paper);
  --text-on-inverse:#EDECE8;
  --focus-ring:     var(--gold-500);
}
```

**Contrast rules (WCAG AA — enforce these):**
- **Oxblood** on paper ≈ 8:1 → safe for text, buttons, icons. Paper text on
  oxblood → safe. Primary button = oxblood fill + paper text.
- **Champagne gold FAILS** small-text contrast on paper (~2.2:1). Gold is allowed
  only: on ink/inverse surfaces, as ≥24px display accents, borders/dividers,
  icons, and focus rings. **Never** gold small body text on a light surface.
- Body text uses ink neutrals (`--n-700/800/900`); muted uses `--n-500`.

### 1.2 Typography

Pick a display face with architectural/crafted character (not the editorial
Playfair default) and a precise UI face that stays legible in dense tables.
Self-host via `@font-face`.

- **Primary pairing:** Display = **Fraunces** (variable; larger optical size,
  medium contrast, restrained) · UI = **Satoshi** or **Inter** · Data = the UI
  face with `font-variant-numeric: tabular-nums`.
- **Alternative:** Display = **Libre Caslon Display** · UI = **Geist**.

```css
:root {
  --font-display: "Fraunces", Georgia, serif;
  --font-ui: "Satoshi", "Inter", system-ui, sans-serif;

  --step--1:0.833rem; --step-0:1rem; --step-1:1.2rem; --step-2:1.44rem;
  --step-3:1.728rem; --step-4:2.074rem; --step-5:2.488rem; --step-6:2.986rem;
  --leading-tight:1.15; --leading-normal:1.5;
  --tracking-tight:-0.01em; --tracking-caps:0.06em;
}
```
Display face for page titles, KPI numbers, and the signature pipeline labels only.
Everything else uses the UI face. All numeric/financial/inventory cells use
tabular figures so columns align.

### 1.3 Space, radius, elevation, motion

```css
:root {
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px;
  --sp-6:32px; --sp-7:48px; --sp-8:64px;

  --r-sm:8px; --r-md:12px; --r-lg:16px; --r-pill:999px;

  --shadow-sm:0 1px 2px rgba(28,29,31,.06);
  --shadow-md:0 4px 12px rgba(28,29,31,.08);
  --shadow-lg:0 12px 32px rgba(28,29,31,.12);

  --dur-instant:80ms; --dur-fast:140ms; --dur-base:220ms;
  --dur-slow:360ms; --dur-page:480ms;
  --ease-out:cubic-bezier(0.2,0,0,1);
  --ease-inout:cubic-bezier(0.4,0,0.2,1);
}
@media (prefers-reduced-motion: reduce) {
  * { animation-duration:0.01ms !important; transition-duration:0.01ms !important; }
}
```

**Deliverables:** `design/tokens.css`, a `ThemeProvider`, self-hosted fonts, and a
Storybook "Foundations" page.
**Acceptance:** every downstream color/spacing value references a token (no raw hex
outside `tokens.css`); reduced-motion honored; contrast rules pass an automated
check.

**⏹ Stop here.** Phase 1 is complete. Do not start Phase 2 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 2 — Primitive component library

Rebuild the shared UI kit on Radix primitives styled with tokens. Each primitive
ships every interaction state and a motion hook.

- **Set:** Button (primary/secondary/ghost/danger), Input, Textarea, Select,
  Combobox, Checkbox, Radio, Switch, Slider, Badge/Tag, Tooltip, Dialog/Modal,
  Drawer/Sheet, DropdownMenu, Tabs, Breadcrumb, Pagination, Toast, Avatar,
  Skeleton, EmptyState, Card, Banner/Alert.
- **States:** default / hover / active / focus-visible / disabled / loading — all
  token-driven. Focus-visible = 2px `--focus-ring` (gold) offset ring.
- **Density:** a compact variant for data-heavy admin tables.
- **Motion:** press = subtle scale (0.98) at `--dur-instant`; hover elevation via
  shadow token; dialogs/sheets animate with Framer Motion (fade + 8–12px rise).
- **Copy:** action labels say what happens ("Onboard company", "Reset password"),
  and the resulting toast uses the same verb ("Company onboarded").

**Deliverables:** components in `shared/ui/`, each with a Storybook story covering
all states.
**Acceptance:** keyboard-operable, visible focus, no raw hex, every state present,
reduced-motion respected.

**⏹ Stop here.** Phase 2 is complete. Do not start Phase 3 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 3 — App shell & responsive navigation

One shell, two skins (admin, client). Establishes the responsive foundation the
rest inherits.

- **Desktop:** collapsible left sidebar on an inverse (ink) surface with gold
  hairline active indicators; top bar with page title (display face),
  breadcrumbs, command palette (Radix Dialog + list), user menu.
- **Mobile (< 768px):** sidebar becomes a slide-in drawer; primary destinations
  collapse to a **bottom tab bar** for the client app; top bar condenses to
  title + menu + search icon.
- **Breakpoints:** `sm 640 · md 768 · lg 1024 · xl 1280 · 2xl 1536`.
- **Page scaffold:** consistent PageHeader (title, description, primary action)
  and content container used by every screen.

**Deliverables:** `AppShell`, `Sidebar`, `TopBar`, `CommandPalette`, `MobileNav`,
`PageHeader`.
**Acceptance:** navigation is intentional at 375px, 768px, 1280px; 44px minimum
touch targets; safe-area insets respected.

**⏹ Stop here.** Phase 3 is complete. Do not start Phase 4 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 4 — Data-dense surfaces

Tables, forms, and dashboards — where "premium" is won or lost.

- **Tables (TanStack):** sortable/filterable/paginated; sticky header; zebra via
  `--surface-sunken`; tabular numerics; row hover; bulk-select. **On mobile each
  row collapses into a card** (label–value stack) rather than horizontal scroll.
- **Forms:** consistent field layout, inline validation in the interface's voice,
  grouped sections, sticky action bar on long forms. Onboarding and PM stage flows
  use a Stepper/Wizard pattern.
- **Dashboards:** KPI cards (display-face numbers, gold hairline detail), themed
  Recharts/visx (oxblood series, gold highlight, ink axes on paper). Skeleton,
  empty, and error states that say what happened and how to fix it.

**Acceptance:** a 20-column table is usable at 375px via card collapse; charts read
clearly in the palette; every async surface has skeleton + empty + error states.

**⏹ Stop here.** Phase 4 is complete. Do not start Phase 5 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 5 — Signature moments & module UX passes

Per-surface polish, plus the one signature element.

- **★ PM stage-gate pipeline (signature):** the 16 stages as a crafted process
  spine — horizontal rail on desktop, vertical timeline on mobile — showing each
  stage's state, blocking gates, and the active approval. Gold marks the current
  gate; oxblood marks a rejected/held stage; transitions animate along the rail.
  This is the product's memorable screen.
- **Admin:** onboarding wizard, capacity/storage/activity dashboard, company
  detail, seat management, and the **RBAC role matrix** (resource × NONE/VIEW/
  READ/WRITE) as a clean, keyboard-navigable grid.
- **Client:** Dashboard (quick actions, activity panel), **calendar** (premium
  month/week/day with module color-keys), CRM **pipeline kanban**, Inventory
  stock views, Finance statements/invoices, Settings.

**Acceptance:** the pipeline is legible and beautiful at mobile and desktop; each
module uses the shared shell, tables, and states — no bespoke one-offs.

**⏹ Stop here.** Phase 5 is complete. Do not start Phase 6 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 6 — Motion & polish

Give motion a consistent language; restraint reads as premium.

- Page/route transitions (crossfade + slight rise, `--dur-page`), list stagger on
  first paint, chart draw-in, toast/drawer choreography, stage-transition
  animation on the PM rail.
- Keep it fast (`--dur-fast`/`--dur-base`) and purposeful; cut anything decorative.
- **Reduced-motion** path verified on every animated surface.

**Acceptance:** no animation exceeds `--dur-page`; disabling motion leaves every
flow fully usable.

**⏹ Stop here.** Phase 6 is complete. Do not start Phase 7 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 7 — Responsive & mobile-web hardening

A dedicated pass across every screen at mobile widths.

- Audit 360/375/390/414px and tablet 768/834px.
- Touch targets ≥ 44px; inputs ≥ 16px font to prevent iOS zoom; bottom sheets for
  mobile actions; sticky headers; safe-area insets; no horizontal scroll.
- Convert remaining wide tables to card/stack; verify calendar and PM pipeline on
  mobile; test forms and onboarding on a phone viewport.

**Acceptance:** every route is beautiful and fully operable on a 375px viewport;
no layout breaks between 360px and 1536px.

**⏹ Stop here.** Phase 7 is complete. Do not start Phase 8 — wait for the user to
run, test, and review, then explicitly say to continue.

---

## Phase 8 — Accessibility, theming & visual QA

- **A11y:** WCAG AA contrast everywhere (re-check all gold usage), full keyboard
  paths, ARIA on the RBAC matrix, calendar, and PM pipeline, `focus-visible`
  rings, screen-reader labels, semantic landmarks.
- **Optional dark theme:** ink is already the base — offer dark mode by swapping
  surface/text token values; gold and oxblood shine on dark.
- **QA:** Storybook covers every component/state; Playwright visual-regression
  snapshots for key screens at mobile + desktop; an automated contrast test in CI.

**Acceptance:** AA passes, keyboard-only completes core flows, visual snapshots are
committed as the baseline.

**⏹ Stop here.** Phase 8 is complete — this is the final phase and the initiative
is done. Stop and wait for the user's final review and sign-off before any merge.
