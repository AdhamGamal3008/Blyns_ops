# LANDING_PAGE.md — public marketing site + discovery booking

The public front door for Blyns. A single long-scroll marketing page, **routed
away from both portals**, that sells the platform as *"an operating system built
around the way your company actually runs."* Its one functional feature is a
**discovery-session booking form** whose submissions surface in the **admin
portal** as leads.

This doc is the definition of done. Build to its section inventory, data model,
endpoints, RBAC, and **Acceptance criteria**.

> **Redesign (2026-08) — read first.** The landing was rebuilt to *attract* rather
> than match the product. It no longer reuses the product's design system: it has
> its **own dark, editorial visual language** — warm near-black canvas, ivory ink,
> a single terracotta accent, self-hosted **Instrument Serif** (display) + **Space
> Mono** (labels) + Inter (body), all scoped under `[data-surface="landing"]` — and
> a small framer-motion **motion kit** (reveals, word-by-word reveal, marquee,
> magnetic CTAs, counter preloader). Layout + motion inspiration: the **ASHCROFT**
> studio Framer template (no asset reused). The **content, routing, booking
> feature, RBAC, and acceptance criteria below are unchanged** — only the visual
> language, arrangement, and motion were rebuilt. File shape under
> `frontend/src/landing/`: `theme/` (tokens + fonts), `motion/`, `ui/` (Section,
> Heading, SectionLabel, PillLink), `chrome/` (Preloader, LandingNav,
> LandingFooter, LiveClock), `sections/`, `showcase/` (the real product screens,
> code-split + lazy-mounted on the Platform section). Where §1/§5 below say "reuses
> the design system verbatim," this note supersedes them.

---

## 1. Positioning & tone

- **Premium, architectural** — closer to a luxury studio than a SaaS vendor.
  Craftsmanship words (*crafted, engineered, tailored, refined, built*), never
  *optimized / streamlined / digital transformation*.
- **Avoid the word "ERP."** Refer to the product as *your company's operating
  system / the system behind exceptional projects*.
- **Its own dark, editorial visual language** (see the redesign note above) — warm
  near-black canvas, ivory ink, a single terracotta accent, self-hosted
  **Instrument Serif** (display) + **Space Mono** (labels) + Inter (body), scoped
  under `[data-surface="landing"]` so it never leaks into the portals.
- Inspiration for **layout + motion patterns only** (full-bleed serif hero, gallery
  grid, numbered disciplines, horizontal scroll timeline, FAQ accordion, big-type
  sections, counter preloader, word-by-word reveals): the **ASHCROFT** studio
  Framer template. **No asset from it is reused.**

## 2. Surfaces & routing

- The landing is its **own top-level surface**: `frontend/src/landing/`. It
  imports neither `AdminShell` nor `ClientShell`, holds no auth token logic, and
  triggers no authenticated API calls except the public booking POST.
- Routes (`frontend/src/App.tsx`):
  - `/` → `LandingPage` (public, no guard).
  - `/app/*`, `/admin/*` portals unchanged.
  - The catch-all `*` redirects to `/` (was `/app`).
- Booking submissions are **Blyns's own leads → control-plane data**, surfaced in
  the **admin** portal (not a tenant module).

## 3. Page structure (content × borrowed pattern)

| # | Section (id) | Content headline | Borrowed pattern | Notes |
|---|---|---|---|---|
| Hero | `top` | Your Company Was Built Differently. | Full-bleed serif hero, 2 CTAs | primary → `#book`, secondary → `#platform`; blueprint visual slot |
| 2 | `approach` | Built Around Your Process. Not Ours. | About + step visual | Blueprint → Workflow → Platform SVG motif |
| 3 | `industries` | Every Company Is Different. | Gallery grid | 5 industry cards |
| 4 | `platform` | Designed Around How You Work | Numbered "disciplines" | 6 capabilities, each with a real product screenshot |
| 5 | `configurable` | Nothing Is Generic. | Big-type editorial | Every field / workflow / approval… |
| 6 | `rules` | Your Business. Your Rules. | Full-width quote block | Ink section, huge type, "Done." in champagne |
| 7 | `lifecycle` | From Opportunity To Completion | Horizontal process timeline | 9 nodes — mirrors the real PM lifecycle |
| 8 | `growth` | Built For Growing Companies | Narrative | — |
| 9 | `security` | Security Designed Into Every Layer | Icon grid | Maps to features that actually exist (IP/country controls, rate limiting, audit) |
| 10 | `partner` | More Than Software. A Long-Term Partner. | Narrative | — |
| 11 | `process` | How We Build Your Platform | Numbered steps 01–06 | — |
| 12 | `faq` | Questions We Usually Hear | Accordion | — |
| CTA | `book` | Your Company Isn't Standard. | Contact/CTA + form | The functional booking form |
| — | footer | — | Footer | Wordmark + anchors + copyright |

## 4. The booking feature (only functional piece)

**Flow:** request-style lead capture (no scheduling engine). Prospect submits →
control-plane `discovery_bookings` → visible + actionable in the admin portal.

**Document — control-plane `discovery_bookings`:**
```
{ _id, full_name, work_email, company, phone, industry, company_size,
  preferred_at (optional ISO), message, status, source, created_at, updated_at,
  notes[] }
```
- `industry` ∈ { interior_fit_out, flooring, wall_cladding, custom_furniture,
  general_contractor, other }
- `status` ∈ { new, contacted, scheduled, closed } (default `new`)
- `source` = "landing" (room for future channels)

**Endpoints:**
- `POST /api/v1/public/discovery-bookings` — **unauthenticated**. Server-side
  validation, honeypot field, and IP rate-limited (reuses the existing rate-limit
  middleware). Returns `201` with a minimal confirmation payload only.
- `GET  /api/v1/admin/discovery-bookings` — list + `?status=` filter + paginate.
- `GET  /api/v1/admin/discovery-bookings/{id}` — detail.
- `PATCH /api/v1/admin/discovery-bookings/{id}` — status change + append note.

**RBAC:** new admin resource **`leads`** added to `ADMIN_RESOURCES`
(`control_plane/admin_users/models.py`). System-role defaults: Super Admin
`WRITE`, Operator `WRITE`, Auditor `READ`, Observer `VIEW`. Re-seeding backfills
the new key onto already-seeded roles (`seed_admin_roles`). Every admin write is
**audited** to the control audit log.

**Admin UI:** a new **"Discovery Sessions"** nav item in `AdminShell`, gated on
`leads ≥ VIEW`; a `BookingsPage` with a list (DataTable), a detail drawer, and a
status pipeline.

## 5. Visuals & screenshots

- **100% self-contained** — no stock imagery, no external/paid assets. Visuals =
  (a) real product screenshots of the seeded demo tenant, (b) custom
  blueprint/line-art motifs in CSS/SVG, (c) Fraunces typography.
- Screenshots are captured from the client portal after enriching the demo seed
  (`scripts/provision_demo_tenant.py`) so dashboards/boards look full, then saved
  under `frontend/src/landing/assets/` and wired into §4 (and the hero).

## 6. Build phases

- **A** — landing surface scaffold + `/` route + this spec. *(this phase)*
- **B** — all marketing sections, content-complete + responsive.
- **C** — backend booking module (public + admin routers, `leads` resource,
  audit, indexes, re-seed).
- **D** — booking form + admin "Discovery Sessions" page.
- **E** — enrich demo seed, capture + wire screenshots.
- **F** — tests (backend POST validation/honeypot/rate-limit + admin RBAC/audit;
  frontend form + render + responsive + a11y) and browser-verified polish.

## 7. Acceptance criteria

- [ ] `/` renders the landing with no auth; portals untouched; catch-all → `/`.
- [ ] The landing imports no portal shell and stores no token.
- [ ] Nav anchors smooth-scroll to their sections; sticky header never covers a
      section heading (`scroll-margin-top`).
- [ ] Public POST persists a `discovery_bookings` doc with `status: "new"`;
      rejects missing/invalid fields and honeypot hits; is rate-limited.
- [ ] The booking appears in the admin portal; status changes are audited and
      RBAC-gated on `leads`.
- [ ] Fully responsive (mobile / tablet / desktop); a11y (axe) clean.

## 8. Prove

- Backend: `discovery_bookings` unit/integration tests green (public + admin).
- Frontend: booking-form + landing-render tests green; responsive sweep green.
- Manual: submit on `/`, see it land in `/admin` → Discovery Sessions.
