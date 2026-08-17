# Development → Production

> How a bug fix or a feature travels from your Mac to https://blyns-eg.com.
>
> Companion documents: `DEPLOYMENT_PLAN.md` (why the infrastructure is shaped this
> way) and `DEPLOY_RUNBOOK.md` (server operations). This one is the day-to-day
> loop you will use most.

---

## 0. The shape of it

```
  local change  →  local proof  →  push to main  →  CI green  →  publish image
        ↓                                                              ↓
   (never edit                                              deploy on the server
    the server)                                          pull → up -d → migrate
                                                                       ↓
                                                            verify from outside
```

Two rules underpin everything:

1. **Nothing reaches production that has not passed CI**, and CI runs the same
   checks you ran locally plus a real image build.
2. **The server is never edited by hand.** Its only local state is
   `.env.production` and `deploy/mongo-keyfile` — both secrets, both generated
   there. Everything else is a checkout or an image.

---

## 1. What travels how — read this once, carefully

This is the single most confusing thing about the setup, and the cause of "I
changed it, deployed, and nothing happened".

| You changed… | It reaches production via | What to run on the server |
|---|---|---|
| `backend/app/**` | **the image** | update `ERP_IMAGE` → `pull` → `up -d app` |
| `frontend/**` | **the image** | same as above |
| `scripts/migrate.py` (and any migration) | **the image** | same, then `migrate` |
| `docker-compose.prod.yml` | **`git pull`** | `git pull` → `up -d` |
| `deploy/Caddyfile` | **`git pull`** (bind-mounted) | `git pull` → `up -d caddy` |
| `scripts/backup_mongo.sh` | **`git pull`** (runs on the host) | `git pull` only |
| `deploy/mongo-init/**` | **effectively nothing** | see the warning below |

**`scripts/` exists in both places, and that is deliberate.**
`docker compose exec app python scripts/migrate.py` runs the copy **inside the
image**, so a migration always matches the application version that introduced it.
`./scripts/backup_mongo.sh` runs on the **host**, from the git checkout. Changing
one does not change the other.

> **`deploy/mongo-init/` only ever runs once**, against a genuinely empty data
> directory. Editing it has no effect on a live database. To change something it
> set up, do it by hand:
> `docker compose … exec mongo mongosh -u … --eval '…'`

---

## 2. The normal loop

### a. Change it locally

```bash
# infra (once per session)
docker compose up -d mongo

# backend
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# frontend
cd frontend && npm run dev        # http://localhost:5173
```

Work against `http://localhost:5173`. The app is at `/app`, the admin portal at
`/admin`, the landing page at `/`.

### b. Prove it locally

Do not skip this because CI exists — CI is the safety net, not the first check.

```bash
cd backend
.venv/bin/ruff check app tests ../scripts
.venv/bin/mypy app
.venv/bin/python -m pytest tests/unit -q
.venv/bin/python -m pytest tests/integration/test_<the_area_you_touched>.py -q

cd ../frontend
npx tsc --noEmit
npx vitest run
```

**Run the full backend suite in shards, never in one go** — a single run OOM-kills
the ephemeral mongod about 70% through and produces a connection-refused cascade
that looks like dozens of real failures:

```bash
cd backend
for s in 0 1 2 3; do
  bash -c 'ALL=(); while IFS= read -r f; do ALL+=("$f"); done \
    < <(printf "%s\n" tests/integration/test_*.py | sort)
  F=(); for i in "${!ALL[@]}"; do (( i % 4 == '"$s"' )) && F+=("${ALL[$i]}"); done
  .venv/bin/python -m pytest "${F[@]}" -q'
done
```

If the change is visible in the browser, look at it in the browser.

### c. Ship it

```bash
git add -A
git commit -m "fix(module): what and why"
git push origin main
```

Then wait for CI: https://github.com/AdhamGamal3008/Blyns_ops/actions
Eight jobs — ruff+mypy, tsc+vitest, docker build + smoke test, four pytest shards.

> If a workflow run fails with **zero jobs**, the workflow *file* is invalid —
> GitHub rejects it before scheduling, so there are no logs. Validate with:
> `docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint`

### d. Publish an image

Only after CI is green.

**For a release** — tag it:

```bash
git tag -a v1.0.1 -m "v1.0.1 — <summary>"
git push origin v1.0.1
```

**For an ordinary fix** — no tag needed; run the **Release** workflow manually
(Actions → Release → Run workflow → `main`). It publishes `sha-<commit>`.

Either way the workflow builds, **smoke-tests the candidate**, and only then
pushes. Note the `sha-…` tag from the run summary — that is what you deploy.

### e. Deploy

```bash
ssh blyns@169.58.194.160
cd /opt/blyns
DC="docker compose --env-file .env.production -f docker-compose.prod.yml"

git pull                                    # compose/Caddyfile/host-script changes
sed -i 's|^ERP_IMAGE=.*|ERP_IMAGE=ghcr.io/adhamgamal3008/blyns-erp:sha-<commit>|' .env.production
$DC pull app
$DC up -d app
$DC exec -T app python scripts/migrate.py   # always — it is a no-op when nothing is pending
```

Pin the **`sha-` tag**, not `latest`. `latest` moves, which makes "what is actually
running?" unanswerable and rollback guesswork.

### f. Verify from outside

From your Mac, never from the server — that skips DNS, TLS and the proxy:

```bash
curl -s https://blyns-eg.com/health
curl -s -o /dev/null -w "%{http_code}\n" https://blyns-eg.com/app
```

Then click through the thing you actually changed.

---

## 3. Migrations

Anything that must change **existing tenant data or indexes** needs a migration —
seeds only run at provisioning, so a live tenant never sees them otherwise.

Typical triggers: a bumped `machine_version`, a new `CLIENT_RESOURCE`, a new
unique index, a backfilled field.

**Add to the registry in `scripts/migrate.py`:**

```python
Migration(
    id="0003_short_description",      # APPEND ONLY. Never reorder or rename an id.
    description="What it does, in one line",
    run=_your_function,
)
```

Rules that are not negotiable:

- **Idempotent.** It will be run twice. The applied-id record is an optimisation,
  not the safety mechanism.
- **Additive.** Never destructive, because a rollback runs older code against the
  newer database (§4).
- **Iterate `active` companies only** — suspended tenants may have no live DB.
- **Fail loudly.** The runner stops at the first failure and does *not* record it,
  so a re-run retries. Half-migrated is worse than stopped.

Check before and after:

```bash
$DC exec -T app python scripts/migrate.py --list      # what is pending
$DC exec -T app python scripts/migrate.py --dry-run   # changes nothing
$DC exec -T app python scripts/migrate.py             # apply
```

---

## 4. Rolling back

```bash
sed -i 's|^ERP_IMAGE=.*|ERP_IMAGE=ghcr.io/adhamgamal3008/blyns-erp:sha-<previous>|' .env.production
$DC pull app && $DC up -d app
```

That is the whole procedure — the exact bytes that were running before, no rebuild.

> **Migrations are not rolled back.** They are additive and idempotent precisely so
> an older image can run against a newer database. Before rolling back *across* a
> migration, read what it did. If it was not additive, rolling back is a restore,
> not a redeploy — see `DEPLOY_RUNBOOK.md` §13.

---

## 5. Hotfix — when production is broken now

The order does not change; only the patience does.

1. **Consider rolling back first.** If the last deploy caused it, that is seconds
   and always safe.
2. Fix locally. Write the test that would have caught it — a hotfix without one is
   the same bug scheduled for later.
3. Push. **Wait for CI anyway.** The temptation to skip it is exactly when it earns
   its keep.
4. Run the Release workflow manually, deploy the `sha-` tag.

There is no path that bypasses CI, and adding one would remove the only thing
standing between a bad afternoon and a bad week.

---

## 6. Things that will bite

| Symptom | Cause |
|---|---|
| Deployed, but the change is not there | It travels via `git pull`, not the image (§1) — or you pinned `latest` and it resolved to the old digest |
| Caddyfile edit did nothing | Needs `git pull` **and** `up -d caddy` |
| `mongo-init` edit did nothing | It only runs on an empty data directory. Ever. |
| Compose says a variable is not set | You omitted `--env-file .env.production` |
| Tests fail in a heap near the end of a local run | The mongod OOM. Shard the suite (§2b) |
| CI run failed with no jobs and no logs | Invalid workflow file — run `actionlint` |
| Access log shows one repeated IP | Cosmetic: it logs the socket peer, so everything reads as Caddy. The rate limiter uses the resolved IP — check `rate_limit_windows` |

**Never:**

- edit code on the server (`/opt/blyns` is a checkout — the next `git pull` fights you)
- run `docker compose … up` without `--env-file .env.production`
- deploy `latest` to production
- commit `.env.production`, `deploy/mongo-keyfile`, or anything from `backups/`
- rewrite or reorder a migration id that has ever run

---

## 7. Quick reference

```bash
# local
make dev                  # mongo + backend reload + frontend dev
make lint                 # ruff + mypy + tsc
make migrate-dry          # what would migrate locally

# server  (ssh blyns@169.58.194.160 ; cd /opt/blyns)
DC="docker compose --env-file .env.production -f docker-compose.prod.yml"
$DC ps                    # what is running
$DC logs -f app           # follow the app
$DC exec -T app python scripts/migrate.py --list
./scripts/backup_mongo.sh backup
./scripts/backup_mongo.sh restore backups/<stamp> erp_tenant_<slug>
```
