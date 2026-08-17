# Plan — Production Deployment (Contabo VPS + Docker)

> **This is an implementation plan, not a spec, and nothing here is built yet.**
> A future session must be able to execute it cold. Paths and findings are current
> as of **2026-08-17** (`main` @ `d2b7682`); if a reference has moved, follow the
> real code.
>
> - Non-negotiables carried from `CLAUDE.md`: fully custom, no third-party SaaS /
>   managed queues / external monitoring; database-per-tenant; two auth realms;
>   every write audited; config-driven `local` / `test` / `production`; tests ship
>   with features.
> - Target: one Contabo VPS, one domain, self-hosted MongoDB, Docker.

---

## 0. What we're deploying, in one paragraph

A single origin serves everything: the marketing landing page at `/`, the client
app at `/app`, the admin portal at `/admin`, and the API at `/api/v1`. That is
already how the code is written — `frontend/.env.production` sets
`VITE_API_BASE=/api/v1` and the backend can mount the built SPA at `/` — so there
is **no CORS in production and no second web server**. One Docker image (React
build + FastAPI) sits behind a reverse proxy that terminates TLS, with MongoDB
running as a container on the same host, its data on a named volume, reachable
only from the Docker network. Deploys are `git push` → build → `docker compose up
-d` → run pending migrations.

---

## 0a. Locked answers (2026-08-17)

| | Answer | Consequence |
|---|---|---|
| **Domain (Q3)** | **`blyns-eg.com`** — **purchased from GoDaddy 2026-08-17** | Config is wired for it (`ERP_DOMAIN`, CORS, Caddy serves apex + `www`). **No DNS record can be created until the VPS has an IPv4**, so this is a Phase E step — the exact records are in Phase E. Registrar credentials are never needed by me. |
| **VPS (Q4)** | Contabo **6 vCPU · 12 GB RAM · 200 GB SSD · 300 Mbit/s**, unlimited traffic | Comfortable. Mongo's WiredTiger cache defaults to ~50% of RAM which would take ~5.5 GB, so it is **capped explicitly** (§Phase C) to leave the app and Caddy predictable headroom. 200 GB is ample: GridFS uploads live in the tenant databases, so disk is the thing to watch long-term (Phase F). |
| **Q5 / Q6** | still open | Phase D's image-push step and Phase C's off-box backup destination wait on these. Everything else proceeds. |

> **On Q5, given the specs:** the original recommendation (Actions → GHCR) partly
> assumed a small VPS where an image build would compete with serving traffic. At
> 6 vCPU that no longer holds and building on the box is viable. GHCR still wins
> on reproducible SHA-tagged images, one-command rollback, and keeping a build
> toolchain off production — but it is now a preference, not a necessity.

## 1. Decisions to lock before Phase B  (my recommendation in **bold**)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Mongo location | **container on the same VPS** · separate VPS · Atlas | **Container on the same VPS.** Atlas is third-party SaaS (rule 1). A separate VPS doubles cost for load you don't have yet. |
| D2 | Mongo topology | standalone · **single-node replica set** | **Single-node replica set.** Same resource cost, but enables transactions and change streams later. See G-3 — the spec claims transactions are needed; today's code uses none. |
| D3 | Reverse proxy | **Caddy** · nginx + certbot | **Caddy.** Automatic Let's Encrypt issue + renewal in ~5 lines of config. nginx needs certbot, a renewal timer, and a reload hook. |
| D4 | Image build location | **GitHub Actions → GHCR** · build on the VPS | **Actions → GHCR** (free for private repos). Building on a 2-core VPS competes with the running app; a pull is seconds. Fallback documented if you'd rather not use Actions. |
| D5 | Frontend delivery | **baked into the backend image** · separate nginx container | **Baked in.** `VITE_API_BASE=/api/v1` already assumes same origin; a second container adds a proxy hop and a CORS surface for no gain at this size. |
| D6 | Deploy trigger | **manual `make deploy` over SSH** · auto-deploy on push to main | **Manual.** With one environment and no staging, auto-deploy on green means a bad merge is live before you look at it. |
| D7 | Backup destination | local disk only · **local + off-box** | **Local + off-box.** A backup on the same disk does not survive the failure it exists for. Needs an answer to Q6. |

---

## 2. Baseline — what already exists (verified, read this before writing code)

| Thing | Where | State |
|---|---|---|
| Backend image | `backend/Dockerfile` | Exists. python:3.12-slim, installs from `pyproject.toml`, copies `app/`, drops to uid 10001, 4 uvicorn workers. **Backend only — no frontend.** |
| Image hygiene | `backend/.dockerignore` | Exists and correct: excludes `.venv/`, `tests/`, `.env*`, caches. |
| Local infra | `docker-compose.yml` | Dev only. Standalone `mongo:7` + optional mongo-express under a `tools` profile. Not a production topology. |
| Production config guard | `core/config.py` `production_problems()` / `validate_for_production()` | **Strong.** Refuses to start in production on a weak/short `ERP_JWT_SECRET`, open `/docs`, empty or localhost CORS, or a localhost Mongo URI. Lists every violation at once. |
| Env-driven behaviour | `core/config.py`, `main.py` | `/docs` auto-off in production; rate limiter auto-switches to the Mongo-backed store when `env == "production"`; logging switches to structured JSON. |
| SPA serving | `demo_gate.mount_built_frontend`, `main.py` (last mount) | Opt-in via `SERVE_FRONTEND`; serves `frontend/dist` with SPA fallback. Greedy mount at `/`, correctly registered after all routers. |
| Demo gate | `app/demo_gate.py` | Opt-in via `DEMO_GATE_ENABLED`, outermost middleware. **Must stay off in production.** |
| Health | `GET /health` | Mongo ping + env + version; 503 when Mongo is down. Ready for a container healthcheck and uptime polling. |
| Uploads | `core/storage.py` | GridFS **inside each tenant DB** — no separate object store, no extra volume. Capped by `ERP_MAX_UPLOAD_MB` (25). |
| Seeding | `scripts/seed_control_plane.py`, `provision_demo_tenant.py` | Control-plane seed creates the first super admin + admin roles. |
| Ad-hoc migrations | `scripts/migrate_projects_v3.py`, `migrate_projects_v4.py`, `backfill_tenant_roles.py` | Idempotent, but run **by hand**, in an order only a human knows. |
| Build targets | `Makefile` | `build-prod` builds the frontend and the backend image separately. |

---

## 3. Gaps this plan closes (found by reading the code, not assumed)

1. **The image cannot serve the SPA.** `mount_built_frontend` resolves
   `Path(main.py).parents[2] / "frontend" / "dist"`. Inside the image `main.py` is
   `/app/app/main.py`, so that path is **`/frontend/dist`** — and the Dockerfile
   copies only `app/`. Setting `SERVE_FRONTEND=1` on today's image raises
   `RuntimeError` at startup. Needs a multi-stage build and a path that works in
   both layouts. *This is the single biggest blocker.*
2. **No migration runner.** `ENVIRONMENTS.md` §4 promises "a versioned migration
   runner … on deploy, iterate tenants and run pending migrations idempotently."
   It does not exist. Today a deploy that changes a `machine_version` needs
   someone to remember which script to run — the exact failure G-1 of the
   configurations work warned about.
3. **No CI.** `.github/` is absent. Nothing stops a red commit reaching `main`.
4. **`ERP_IP_TRUSTED_PROXIES` is empty.** Behind a reverse proxy that means every
   request's client IP is *the proxy's*, so all users share one rate-limit bucket
   and IP allow/deny rules are meaningless. Must list the proxy. (Empty is the
   correct *default* — it refuses to trust a spoofable header — but it is wrong
   once a proxy is in front.)
5. **No production env template or secret-generation runbook.**
6. **No backups**, despite `ENVIRONMENTS.md` §4 promising per-tenant `mongodump`.
7. **No container healthcheck**, so Docker cannot restart a wedged app.
8. **Repo housekeeping**: 9 merged branches, 1 superseded branch, 1 untracked doc,
   demo artifacts in the local dev DB.

---

## 4. Phases

Sizes: **S** ≈ ½ day · **M** ≈ 1–2 days · **L** ≈ 3–5 days.
Each phase ends with a **Prove** that must pass before the next begins.

### Phase A — Local code cleanup  **(S)**
Housekeeping only; no behaviour changes. Doing it first means everything after is
built on a tree you can reason about.

- **Branches** *(decided 2026-08-17)*. All 9 merged branches were `ahead=0` —
  no commit on any of them was missing from `main`. **Remote copies of the 4 that
  had them are deleted** (`pm-v2-workflow` `0f090fc`,
  `quick-actions-personalization` `2ea47ca`, `projects-analytics` `9679f43`,
  `landing-redesign` `9662696`) so GitHub shows only `main` once CI lands in
  Phase D; **all 9 local branches are kept** as the owner's personal history.
  `landing-page` was 3 commits ahead but superseded — `git cherry` marked all
  three patch-equivalent to commits in `main` — and is **deleted** local + remote
  (recovery SHA `e9762af`).
- **`docs/PROJECT_MANAGEMENT_LIFECYCLE.md`** *(decided 2026-08-17)*: **stays
  untracked on the owner's machine.** It describes the old 16-stage machine
  (current is 9-stage v2.0), so it must never be committed as if it were current.
  Every commit in this repo must continue to exclude it.
- **Local dev database** — the demo artifacts from the configurations proves (the
  "Flooring — ASTM" configuration and `PRJ-0002` in the `acme` tenant). Local
  only; does not affect production. Owner's call whether to keep them as demo
  data.
- **`.demo-backend.log`** is gitignored but present — delete.
- Confirm lint and the batched test suite are green on a clean tree.

**Prove:** `git branch -a` lists only `main` plus anything you intend to keep;
working tree clean apart from deliberate files; lint + tests green.

### Phase B — Local code prep + Docker prep  **(M)**
The real engineering. Everything here is verifiable on your Mac before a VPS
exists.

- **Multi-stage Dockerfile** (`backend/Dockerfile` → repo-root `Dockerfile`, since
  it now needs both trees):
  - stage 1 `node:22-alpine` — `npm ci`, `npm run build` with
    `VITE_API_BASE=/api/v1`;
  - stage 2 `python:3.12-slim` — install from `pyproject.toml`, copy `app/`, copy
    `--from=build /frontend/dist` to a path the app resolves in-image;
  - `HEALTHCHECK` hitting `/health`;
  - keep the non-root user and the 4 workers.
- **Fix the dist-path resolution** so `mount_built_frontend` works in *both* the
  repo layout and the image layout — ideally an `ERP_FRONTEND_DIST` setting
  defaulting to today's relative path. Test both.
- **Root `.dockerignore`** covering `node_modules/`, `dist/`, `.venv/`, `.git/`,
  `**/.env*`.
- **`docker-compose.prod.yml`**: `app` + `mongo` + `caddy`, an internal network,
  a named Mongo volume, `env_file`, `restart: unless-stopped`, healthchecks,
  and **no published Mongo port** (Mongo reachable only inside the network).
- **`.env.production.example`** — every var the production guard demands, with
  generation commands (`openssl rand -hex 32`) and a comment on
  `ERP_IP_TRUSTED_PROXIES` explaining gap #4.
- **Migration runner** `scripts/migrate.py`: an ordered registry of named,
  idempotent migrations; applied state recorded in the control DB; iterates every
  active tenant; `--dry-run`; safe to re-run. Fold the existing v3/v4/backfill
  scripts in as the first registered entries.
- **`Makefile`** targets: `build-image`, `run-prod-local`, `migrate`, `deploy`.

**Prove:** the image running with `ERP_ENV=production` and a strong secret serves
the landing page at `/`, the app at `/app`, the admin portal at `/admin`, and
`/health` returns `ok`; `scripts/migrate.py --dry-run` reports pending migrations
and running it twice is a no-op the second time.

> **On `/docs`:** the original wording here said it must return **404**. That is
> wrong for a same-origin SPA. The SPA is mounted catch-all at `/`, so *any*
> unmatched path returns `index.html` with **200** — that is what client-side
> routing needs. The check that actually matters is that **no Swagger UI is
> served**: `curl /docs` must return the SPA shell with zero occurrences of
> "swagger" or "redoc". FastAPI's `docs_url` really is `None` in production.

### Phase C — MongoDB server prep  **(S)**
- `mongo:7` container, single-node **replica set** (`--replSet rs0`), initiated
  once via `rs.initiate()` with the container hostname.
- **Authentication on**: a root user created on first boot from a compose secret,
  then a least-privilege application user restricted to the control DB and the
  `erp_tenant_*` pattern. `ERP_MONGO_URI` becomes
  `mongodb://<user>:<pass>@mongo:27017/?replicaSet=rs0&authSource=admin`.
- **Not published to the host** — no `ports:` entry, so it is reachable only from
  the app container. This matters more than TLS here: Contabo VPSs are on the
  public internet and an exposed 27017 is scanned within minutes.
- Volume on the host disk, with the data path documented for backups.
- **Backup script** `scripts/backup_mongo.sh`: per-tenant `mongodump` (trivially
  per-company — each is its own database), timestamped, retention window, plus a
  **restore-one-tenant** path. Cron nightly. Off-box copy per **D7**/**Q6**.

**Prove:** `rs.status()` shows a healthy single-node set; the app connects with
the least-privilege user; `docker compose down && up` preserves data; a backup
taken, one tenant dropped, and that tenant restored from the dump alone.

> **Every compose command needs `--env-file .env.production`.** `env_file:` only
> populates a *container's* environment; `${VAR}` interpolation in the compose
> file itself reads the shell or a file named exactly `.env`. Without the flag,
> `MONGO_ROOT_USER`, `ERP_DOMAIN` and friends silently become empty strings.

### Phase D — GitHub sync + CI  **(S)**
- **CI** (`.github/workflows/ci.yml`) on push and PR to `main`: ruff, mypy, `tsc`,
  the frontend suite, and the backend suite **in batches** — a single full pytest
  run OOM-kills the ephemeral mongod about 70% through and produces a
  connection-refused cascade that looks like real failures but isn't.
- **Image build + push to GHCR** on tagged releases (or manual dispatch), tagged
  with the commit SHA so a deploy is reproducible and a rollback is a re-tag.
- Branch protection on `main`: require CI green. Answer to **Q5**.
- Confirm `.gitignore` still excludes every env file before anything is pushed.

**Prove:** a PR with a deliberately failing test is blocked by CI; a tagged
release produces a pullable GHCR image; `docker run` of that image starts.

### Phase E — Server deployment (Contabo)  **(M)**
- **Host hardening**, before anything is installed: non-root sudo user, SSH
  **key-only** (`PasswordAuthentication no`), `ufw` allowing only 22/80/443,
  `fail2ban` on sshd, unattended security upgrades, hostname + timezone.
- **Docker Engine + compose plugin** from Docker's own apt repo (not the distro's
  older packages).
- **DNS at GoDaddy** — `blyns-eg.com` is registered (2026-08-17). Nothing can be
  configured until the VPS exists and has an IPv4, because these records point at
  it. Once it does, in GoDaddy's **Domain → DNS → Manage Zones**:

  | Type | Name | Value | TTL |
  |---|---|---|---|
  | `A` | `@` | *the VPS IPv4* | 600 |
  | `A` | `www` | *the VPS IPv4* | 600 |
  | `AAAA` | `@` | *the VPS IPv6*, if Contabo provides one | 600 |
  | `AAAA` | `www` | *the VPS IPv6*, if provided | 600 |

  Then **delete GoDaddy's default parking records** — a fresh domain ships with an
  `A @` pointing at GoDaddy's parking page and often a `CNAME www`. Both conflict
  with the records above; a leftover `CNAME www` in particular silently wins over
  the `A www`.

  - **Use GoDaddy's own nameservers.** Putting Cloudflare in front would add a
    third party to every request (rule 1), and its proxy mode changes which IP the
    backend sees — which is exactly the `ERP_IP_TRUSTED_PROXIES` trap in G-2.
  - **TTL 600, not the 1-hour default**, so a mistake is 10 minutes to fix rather
    than an hour. Raise it after go-live.
  - **Verify before starting Caddy:** `dig +short blyns-eg.com` and
    `dig +short www.blyns-eg.com` must both return the VPS IP. Starting Caddy
    early fails the ACME challenge and burns Let's Encrypt's 5-failures-per-
    hostname-per-hour budget (G-8).
  - **Email is unaffected.** No MX records are involved, so adding mail on this
    domain later is independent of anything here — see G-4 and **Q8**.
- **Caddyfile**: the domain, `reverse_proxy app:8000`, automatic HTTPS, HTTP→HTTPS
  redirect, compression, and security headers (HSTS, `X-Content-Type-Options`,
  `Referrer-Policy`, a frame-ancestors policy).
- **Secrets on the box**: `/opt/blyns/.env.production`, `chmod 600`, owned by the
  deploy user, never in the repo. Generate `ERP_JWT_SECRET` **on the server**.
- **Set `ERP_IP_TRUSTED_PROXIES`** to the Caddy container's network address
  (gap #4). Verify afterwards that the access log shows real client IPs, not the
  proxy's.
- **`ERP_CORS_ORIGINS`** to the real origin (belt-and-braces — same-origin means
  CORS is not exercised, but the production guard requires it non-localhost).
- **First run**: pull image → `docker compose up -d` → `scripts/migrate.py` →
  `seed_control_plane.py` → change the printed super-admin password immediately.
- **Deploy runbook** in `docs/DEPLOY_RUNBOOK.md`: deploy, roll back, restore a
  tenant, rotate the JWT secret (and that it logs everyone out), read logs.

**Prove:** `https://<domain>` serves the landing page with a valid certificate;
you can log into the admin portal and the client app; `/api/v1/health` is `ok`;
`/docs` is 404; Mongo is unreachable from outside the host
(`nc -z <ip> 27017` fails); rebooting the VPS brings everything back unattended.

### Phase F — Go-live + operations  **(S)**
- Onboard the first real tenant through the admin portal; walk one project through
  a stage gate to confirm the machine runs in production.
- **Uptime check** hitting `/health` — self-hosted (a cron on another box you own)
  to stay inside rule 1, or accept a free external pinger as an explicit exception
  (**Q7**).
- **Log rotation** for Docker JSON logs (they grow unbounded and fill the disk —
  a classic first-outage cause).
- **Disk-space alerting**: GridFS uploads live in Mongo, so tenant documents grow
  the database volume directly.
- Document a monthly restore drill. A backup you have never restored is a
  hypothesis, not a backup.

**Prove:** a restore drill performed and timed; alerting fires on a deliberately
filled disk; the runbook is followed end-to-end by you, not by me.

---

## 5. Gotchas

- **G-1 — the SPA path is the blocker.** Gap #1 makes the current image unable to
  serve the frontend at all. Fix it in Phase B and verify locally; discovering it
  on the VPS wastes a deploy cycle.
- **G-2 — trusted proxies change security posture, not just logs.** With the
  default empty list behind Caddy, every client shares one rate-limit bucket: one
  noisy user can rate-limit *everyone*, and IP allow/deny rules match the proxy.
- **G-3 — the replica-set rationale is stale.** `ENVIRONMENTS.md` §4 says a
  replica set is needed for "multi-document transactions used in inventory
  movements + finance posting", but `start_session` / `with_transaction` appear
  **nowhere** in `backend/app`. Do it anyway (D2) — but as future-proofing, not as
  a blocker, and correct the spec.
- **G-4 — nothing emails anyone.** There is no SMTP anywhere in the backend.
  Discovery bookings land silently in the control DB, so **someone must check the
  admin portal** or leads rot unseen. Decide before you point a domain at it
  (**Q4**).
- **G-5 — the first super-admin password is printed once.** `seed_control_plane.py`
  prints it and never stores it. Capture it at run time and change it immediately.
- **G-6 — migrations are not automatic.** Until Phase B's runner exists, a deploy
  carrying a `machine_version` bump needs its script run by hand or tenants sit on
  a stale machine. This is exactly configurations-plan G-1.
- **G-7 — Python version drift.** The image is 3.12; your local venv is 3.14.
  `requires-python = ">=3.12"` allows both, but CI should test the version the
  image actually ships.
- **G-8 — Let's Encrypt rate limits.** 5 failures per account per hostname per
  hour. Get DNS right before starting Caddy; use its staging endpoint while
  experimenting.
- **G-9 — `ERP_ENV=production` is load-bearing.** It flips the rate limiter to
  Mongo-backed, disables `/docs`, switches logging to JSON, and turns on the
  startup guard. Forgetting it yields a superficially working but unsafe server.

---

## 6. What I need from you

**Blocking — Phase B cannot start without these:**

- **Q1** — Delete the 9 merged branches and the superseded `landing-page`, locally
  and on `origin`? (I'll show you each one's status before deleting anything.)
- **Q2** — `docs/PROJECT_MANAGEMENT_LIFECYCLE.md`: delete, or rewrite against the
  current 9-stage machine?
- **Q3** — **The domain name**, and where you'll buy it. Needed for the Caddyfile,
  `ERP_CORS_ORIGINS`, and DNS. Also: apex + `www`, or a subdomain like
  `app.<domain>`?

**Blocking — Phase E cannot start without these:**

- **Q4** — Contabo VPS specs: RAM, vCPU, disk, OS image. Mongo + app + Caddy on
  4 GB is fine at your size; 2 GB is tight once Mongo's cache and 4 uvicorn
  workers are both resident. Also confirm the region.
- **Q5** — GitHub Actions + GHCR acceptable (**D4**), or build on the VPS?
- **Q6** — Where do off-box backups go? Any storage you already own (another VPS,
  a NAS, an S3-compatible bucket) — or is local-only acceptable for now, with the
  risk understood?

**Non-blocking, but decide before go-live:**

- **Q7** — Uptime monitoring: self-hosted cron, or accept a free external pinger
  as a deliberate exception to rule 1?
- **Q8** — Who watches discovery bookings (G-4)? If nobody, should I remove the
  public booking form from the landing page rather than collect leads into a void?
- **Q9** — Is this a hard launch (real customers immediately) or a soft one (you
  and a pilot tenant first)? It changes how much of Phase F is required up front.

**What I do *not* need:** any password, API token, SSH key, or `.env` contents.
When we reach Phase E I will give you the exact commands to run on the server and
you will run them yourself; secrets get generated on the box and never pass
through this conversation.

---

## 7. Suggested order and rough effort

| Order | Phase | Size | Can start |
|---|---|---|---|
| 1 | A — Local cleanup | S | now (needs Q1, Q2) |
| 2 | B — Code + Docker prep | M | after Q3 |
| 3 | D — GitHub sync + CI | S | in parallel with B (needs Q5) |
| 4 | C — Mongo prep | S | after B (verified locally first) |
| 5 | E — Server deployment | M | after Q4; VPS + domain must exist |
| 6 | F — Go-live + ops | S | after E |

Realistically **4–7 working days** of my time, plus your time on the VPS, the
domain purchase, and DNS propagation. Phases A–D are entirely local: everything is
proved on your Mac before you spend money on a server.

## Build status

### Phase A — Local code cleanup — DONE (2026-08-17)
Housekeeping only; no behaviour changed. Whole suite re-verified on the clean
tree: **501 backend (110 unit + 391 integration, batched) + 213 frontend**;
ruff + mypy + tsc clean.

- **Branches.** `origin` now carries **only `main`** — the 4 stale remote branches
  were deleted (`pm-v2-workflow` `0f090fc`, `quick-actions-personalization`
  `2ea47ca`, `projects-analytics` `9679f43`, `landing-redesign` `9662696`), all of
  them `ahead=0` against `main`. The 9 local branches are kept as the owner's
  history. `landing-page` deleted local + remote (superseded; recovery `e9762af`).
- **`UI_REFACTOR.md` moved to `docs/`.** It is a completed initiative's plan doc
  and every other plan lives in `docs/` — and the file's own line 41 already
  referred to itself as `docs/UI_REFACTOR.md`, so the root copy was the anomaly.
  The two references in `frontend/src/__tests__/motion.test.ts` were repointed.
- **Deleted:** a stale 6 MB `.demo-backend.log`, and a stray root `node_modules/`
  holding nothing but an empty `.vite` cache (there is no root `package.json` —
  it was left behind by running vite from the repo root once).
- **`docs/PROJECT_MANAGEMENT_LIFECYCLE.md` stays untracked**, per the owner. It
  documents the superseded 16-stage machine, so no commit may include it.
- **Left alone:** the local dev database still holds the demo artifacts from the
  configurations proves ("Flooring — ASTM" config + `PRJ-0002` in `acme`). Local
  only, and the owner's data to keep or drop.

**Prove:** `git branch -r` lists only `origin/main`; working tree clean apart from
the deliberately untracked lifecycle doc; lint, typecheck and the full batched
suite green.

### Phase B — Local code prep + Docker prep — DONE (2026-08-17)
The image now builds, runs in production mode and serves the whole product. Gap #1
is closed. Everything below was proved on the Mac; no VPS involved.

- **`Dockerfile` (repo root), multi-stage.** `node:22-alpine` builds the SPA →
  `python:3.12-slim` runtime. Non-root (uid 10001), `HEALTHCHECK` on `/health`,
  4 uvicorn workers. **322 MB**, reports `healthy`.
- **Gap #1 fixed** via a new `ERP_FRONTEND_DIST` setting. The default stays the
  repo layout (`<repo>/frontend/dist`); the image sets `/app/frontend_dist`, which
  is what it actually copies. Both layouts work.
- **`.dockerignore` at the root** — the root build does NOT consult
  `backend/.dockerignore`, so the whole context needed covering.
- **`docker-compose.prod.yml`** — app + mongo + caddy on an internal network.
  Mongo publishes **no port at all** (a Contabo VPS is public; an exposed 27017 is
  found by scanners in minutes) and the app is only reachable through Caddy.
- **`deploy/Caddyfile`**, **`deploy/mongo-init/01-init-replica-set.js`**,
  **`.env.production.example`** (every var the startup guard demands, with
  generation commands and the `ERP_IP_TRUSTED_PROXIES` warning spelled out).
- **`scripts/migrate.py`** — the versioned runner `ENVIRONMENTS.md` §4 has always
  promised. Ordered, append-only registry; applied ids recorded in the control DB;
  `--dry-run`, `--list`, `--force <id>`; stops at the first failure and does not
  record it, so a re-run retries. The three ad-hoc scripts are folded in as
  `0001_backfill_client_roles` and `0002_projects_machine_v4`.
- **Makefile**: `build-image`, `run-prod-local`, `stop-prod-local`, `migrate`,
  `migrate-dry`.

**Two problems found while proving, both of which would have broken the deploy:**

1. **`frontend/.env.production` was gitignored and untracked.** It exists only on
   the owner's machine, so any fresh clone or CI build would run `npm run build`
   without `VITE_API_BASE`, and `api.ts` falls back to
   `http://localhost:8000/api/v1` — shipping a bundle that points **every
   visitor's browser at its own machine**. A build that succeeds and an app that
   cannot reach its server. Now tracked via a `.gitignore` exception (it is
   build-time public config — anything in a `VITE_` var is compiled into the
   downloaded bundle, so it can never hold a secret), **plus** a build-time guard
   that greps the built bundle for `localhost:8000` and fails the image build.
2. **`frontend/package-lock.json` was out of sync with `package.json`**, so
   `npm ci` refused outright — CI in Phase D would have hit the same wall.
   Regenerating on macOS was not enough: `@napi-rs/wasm-runtime` is an *optional*
   package whose `@emnapi/*` peers npm resolves differently per platform, so the
   darwin lockfile still failed on linux. Fixed by regenerating the lockfile
   **inside `node:22-alpine`**; `npm ci` now succeeds on both, and all 213
   frontend tests pass against the refreshed tree.

**Verified:** `/`, `/app`, `/app/projects`, `/admin` all serve the SPA; hashed
assets serve as real files with correct MIME types; `/api/v1/auth/login` returns
the application's own error envelope (so the API is not shadowed by the greedy
mount); `/health` reports `{"status":"ok","mongo":true,"env":"production"}`; logs
are structured JSON; the bundle contains no `localhost`; the container reaches
`healthy`; `migrate.py` applies, is a no-op on re-run, and `--force` re-applies.

### Phase C — MongoDB server prep — DONE (2026-08-17)
An authenticated single-node replica set, the app connecting as a least-privilege
user, and a backup/restore proved by actually destroying and recovering a tenant.

- **`scripts/init_mongo_keyfile.sh`** — generates the replica-set keyfile (mode
  400). A set running `--auth` needs one even with a single member. mongod is
  fussy: the file must also be owned by **uid 999**, and a bind mount keeps the
  *host's* ownership, so the script says so loudly when it cannot chown.
- **`deploy/mongo-init/01-create-app-user.js`** — creates `erpapp` with
  `readWriteAnyDatabase` (needed because tenant databases are created on demand
  and their names are not known ahead of time). Not root: it cannot manage users
  or the replica set.
- **A one-shot `mongo-init` service** initiates the set. **This cannot be done
  from `/docker-entrypoint-initdb.d`** — the entrypoint runs those scripts against
  a temporary mongod started *without* `--replSet`, so `rs.initiate()` there
  configures nothing and the real server comes up with `--replSet` and no config.
  That was the first attempt, and it left the set permanently uninitialised.
- **Mongo's healthcheck asserts PRIMARY**, not merely that it answers a ping. The
  app connects with `replicaSet=rs0`, so `depends_on: service_healthy` must mean
  "a primary exists" — a ping goes green while the driver would still hang in
  server selection.
- **WiredTiger cache capped** (`MONGO_CACHE_GB`, default 4). Left alone it takes
  ~50% of total host RAM — ~5.5 GB of the 12 GB — without knowing the app and
  Caddy share the box.
- **`scripts/backup_mongo.sh`** — per-database dump/list/restore, running
  mongodump *inside* the container so the host needs no MongoDB tooling and the
  database stays unpublished. Restore is guarded by typing the database name.

**Four bugs found by proving rather than assuming:**

1. **Compose interpolation ignored `.env.production`** — `env_file:` fills a
   container's environment, but `${VAR}` in the compose file itself reads the
   shell or a file named exactly `.env`. Every credential silently became an empty
   string. Every compose invocation now passes `--env-file`.
2. **`ERP_MONGO_URI` could not be `source`d** — the `&` between query parameters
   is a shell metacharacter, and `backup_mongo.sh` reads the file with `source`.
   Now quoted in the example (Compose strips quotes).
3. **The app-user script never received its variables.** It correctly refused to
   create a half-configured user — but the Mongo entrypoint logs that and *carries
   on starting*, so the only symptom was an app that could not authenticate.
   `MONGO_APP_USER`/`MONGO_APP_PASSWORD` are now passed to the service.
4. **The backup silently dumped only the FIRST database.** `docker compose exec`
   inherits the `while read` loop's stdin and consumes it, so the loop ran once and
   still reported success — a failure you would discover at restore time. Now the
   list is read into an array first, with a count assertion as a second guard.

**Verified:** `rs0` PRIMARY with auth and keyfile; app healthy connecting as
`erpapp`; control plane seeded and a tenant provisioned; `migrate.py` applied both
migrations **inside the container**; backup produced 2 archives; `erp_tenant_acme`
dropped (control plane untouched) and restored from its archive alone — 41
collections, correct document counts, indexes rebuilt; a full `down`/`up` cycle
preserved everything and `mongo-init` reported "already initiated".

**Also fixed in the image** (found here, belongs to Phase B): `scripts/` was not
copied into it and `PYTHONPATH` was unset, so there was **no way to run a
migration or seed the control plane on a server**. Both corrected; `docker compose
exec app python scripts/migrate.py` now works.

### Phase D — CI — DONE (2026-08-17), image publishing deferred
`.github/workflows/ci.yml` runs on every push and PR to `main`: ruff, mypy, tsc,
the frontend suite, a **production image build with a smoke test**, and the whole
backend suite.

- **The backend suite is sharded across 4 runners**, and the split is computed
  from the directory listing rather than hardcoded. Two reasons, both learned the
  hard way: a single serial run OOM-kills the ephemeral mongod ~70% through, and a
  hardcoded file list lets a newly added test file silently never run. Proved
  locally — 123 + 101 + 148 + 63 = **435 integration tests**, every file covered
  exactly once, longest shard 5m15s.
  - Worth noting: that is **more than the 391** the hand-written batches had been
    running. The computed split immediately picked up files the manual batching
    was skipping, `test_rbac_matrix.py` among them.
- **`mongod` presence is asserted before pytest runs.** `conftest.mongo_uri` calls
  `pytest.skip()` when the binary is missing, so a failed install would otherwise
  produce a green run that executed **zero** integration tests. MongoDB is
  installed from its own apt repository, not a third-party action.
- **The image job builds what we actually ship** and smoke-tests it: starts with
  `ERP_ENV=production` (so a clean start also proves `validate_for_production` is
  satisfied), asserts `/health` is `ok`, asserts the SPA is served, and asserts
  `scripts/migrate.py` is runnable inside the container. This is the only job that
  can catch a broken Dockerfile, a lockfile that fails only on linux, or the
  bundled-`localhost` guard.
- **Python 3.12 / Node 22 pinned to match the image** (G-7).
- **A single `CI` gate job** aggregates the rest, so branch protection can require
  one check and adding a shard later does not mean editing the rule.

**Deferred, pending Q5:** publishing the image to GHCR on a tagged release. The
build is already proved by the `image` job; publishing is only the extra step of
tagging and pushing, and the choice between GHCR and building on the VPS does not
change anything above.

**Owner actions (in GitHub's UI, nothing I can do):**
1. Settings → Branches → add a rule for `main` requiring the **`CI`** check.
2. Decide **Q5**; if GHCR, no secret is needed — `GITHUB_TOKEN` can push to the
   repo's own package registry.

**Phase E is the only phase left before go-live**, and it is blocked purely on the
VPS existing. `blyns-eg.com` is registered; its DNS records need the server's IP.
