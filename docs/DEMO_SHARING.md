# Demo Sharing — operator runbook

Expose your **local** ERP to a client over a temporary public HTTPS URL, gated by
a username + password, using an anonymous **Cloudflare Quick Tunnel**. No
Cloudflare account, no domain, no DNS. It's a **demo tool, not hosting** — the URL
dies when you stop the script, close the terminal, or the laptop sleeps.

Design + rationale live in [DEMO_SHARING_PLAN.md](DEMO_SHARING_PLAN.md).

---

## One-time setup

Install the tunnel binary (not bundled — it's system software):

```bash
brew install cloudflared
```

- Windows: `winget install --id Cloudflare.cloudflared`
- Debian/Ubuntu: install the `.deb` from the cloudflared GitHub releases page.

Make sure **MongoDB is running** locally (the same DB your normal dev backend
uses) — the demo's health check stays red until Mongo answers.

---

## Run a demo

From the **repo root** (do *not* `cd backend` — the script resolves its own paths
and runs uvicorn with `cwd=backend` internally). Use the **backend venv's Python**
(it has `uvicorn` + the app deps; the system `python` does not):

```bash
backend/.venv/bin/python scripts/share_demo.py
```

Or activate the venv once, then plain `python` works:

```bash
source backend/.venv/bin/activate
python scripts/share_demo.py
```

What it does: builds the production frontend → starts a basic-auth-gated backend
on `127.0.0.1:8000` (its own logs go to `.demo-backend.log`, not your console) →
opens the tunnel → **waits for the tunnel edge to become routable** (a Quick
Tunnel's URL is printed a few seconds before it actually works; the script probes
until it's live so the URL you hand out works on the first click) → prints a block
like:

```
====================================================================
  DEMO IS LIVE — send this to the client
====================================================================

  URL       https://<random-words>.trycloudflare.com
  Username  client
  Password  <24-char password>
```

Skip the ~1-minute rebuild if the bundle is already current:

```bash
backend/.venv/bin/python scripts/share_demo.py --skip-build
```

**Stop sharing:** press `Ctrl+C`. The script terminates the backend and the
tunnel and leaves no orphan processes.

---

## What to send the client

- Send the **URL** and the **password** over **two different channels** (e.g. URL
  by email, password by SMS/Signal). Never put both in one message.
- Tell them the browser will show a login prompt — enter the username and
  password exactly as printed.
- Remind them the link is **temporary**: it changes every run and stops working
  the moment you end the session.

---

## Rotate the credentials

The username/password are generated once and cached in `.env.demo` (gitignored,
never committed). To rotate:

```bash
rm .env.demo
python scripts/share_demo.py
```

A fresh 24-character password is generated on the next run. Re-running **without**
deleting the file reuses the same credentials.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `cloudflared is not installed` | Run the install command above, re-run the script. |
| `~/.cloudflared/config.yml exists …` | That file forces named-tunnel mode. Rename it (`mv ~/.cloudflared/config.yml ~/.cloudflared/config.yml.bak`), then re-run. |
| `Backend did not become healthy …` | MongoDB isn't running, or your `backend/.env` is missing/invalid (needs `ERP_JWT_SECRET`, `ERP_MONGO_URI`). Start Mongo / fix `.env`, and check `.demo-backend.log` for the backend's own error output. |
| First client hit shows a Cloudflare error / connection reset | The tunnel edge is still warming up. The script waits for this before printing the URL, but on a slow warmup it prints anyway with a note — give it another few seconds and reload. |
| Client sees a login box but valid creds are rejected | You're likely sending an old password. Re-read the printed banner, or rotate (above). |
| Password prompt **reappears after the client logs into the portal** | Fixed (the gate sets an `erp_demo_gate` session cookie after the first Basic auth). If you still see it, you're running an old copy of the demo — `Ctrl+C` and re-run — or the browser cached a half-state: reload, or use a fresh private/incognito window. |
| Tunnel dropped mid-demo | Quick Tunnels have no SLA. `Ctrl+C` and re-run — you'll get a **new** URL to resend. |
| Client gets 403 (not a login prompt) | You're running against restrictive **IP access rules**. Don't run the demo against production IP config; locally, no rules are seeded. Kill switch: set `ERP_IP_FILTER_ENABLED=false` in `backend/.env`. |
| Frontend loads but API calls 404/CORS-fail | The build didn't pick up the origin-relative base. Run a full build (drop `--skip-build`) so `frontend/.env.production` (`VITE_API_BASE=/api/v1`) is regenerated. |

---

## Security notes

- The gate protects **everything** — API, `/docs`, `/openapi.json`, and the SPA —
  because it's ASGI middleware, not a route dependency.
- After the first Basic auth the gate pins an HttpOnly, SameSite=Lax session
  cookie and admits later requests by it (so the app's Bearer JWT doesn't collide
  with the gate). The cookie is a hash of the credentials — unforgeable without
  the password — and dies with the browser session.
- Nothing here touches the MongoDB port; the database stays bound to `127.0.0.1`.
- The gate is **off** unless the script turns it on. Plain `uvicorn` / `npm run
  dev` are completely unaffected.
- Treat the tunnel as public: anyone with the URL **and** the password can reach
  live data in whatever tenant/DB your local backend points at. Point it at demo
  data, and end the session when you're done.
```
