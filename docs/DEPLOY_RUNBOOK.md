# Deploy Runbook — Blyns ERP on a Contabo VPS

> The operational companion to `docs/DEPLOYMENT_PLAN.md`. That document explains
> *why*; this one is the sequence you actually run.
>
> **Target:** Contabo VPS (6 vCPU / 12 GB / 200 GB), Ubuntu 24.04 LTS,
> `blyns-eg.com` (GoDaddy).
> **Everything runs on the server** unless a step says otherwise.
>
> Secrets are generated **on the box** and never leave it. Nothing in this file
> asks you to paste a password, key or token into a chat.

---

## 0. Before you start

Have ready:

- The VPS **IPv4** (and IPv6 if Contabo gave you one), and the initial root
  password from their email.
- Access to **GoDaddy DNS** for `blyns-eg.com`.

No GitHub token is needed: the repository is public and so is the published
image (§5).

Conventions below: `you@laptop$` runs on your Mac, `root@vps#` / `blyns@vps$` on
the server.

---

## 1. First login and a non-root user

Never run the stack as root, and never keep password SSH open on a public IP —
Contabo addresses are scanned within minutes of allocation.

```bash
you@laptop$ ssh root@<VPS_IP>          # initial password from Contabo
```

```bash
root@vps# adduser blyns                 # set a strong password when prompted
root@vps# usermod -aG sudo blyns
root@vps# mkdir -p /home/blyns/.ssh && chmod 700 /home/blyns/.ssh
```

From your Mac, in a **second terminal**, install your key:

```bash
you@laptop$ ssh-keygen -t ed25519 -C "blyns-vps"     # only if you have no key yet
you@laptop$ ssh-copy-id blyns@<VPS_IP>
```

**Verify key login works before locking anything down:**

```bash
you@laptop$ ssh blyns@<VPS_IP> "echo key login OK"
```

> If that fails, stop and fix it. The next step disables password login — running
> it while key auth is broken locks you out of your own server.

## 2. Harden SSH, firewall, updates

```bash
blyns@vps$ sudo sed -i \
  -e 's/^#\?PermitRootLogin.*/PermitRootLogin no/' \
  -e 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' \
  /etc/ssh/sshd_config
blyns@vps$ sudo systemctl restart ssh
```

Keep your current session open and confirm a **new** terminal can still connect
before closing it.

```bash
blyns@vps$ sudo apt update && sudo apt upgrade -y
blyns@vps$ sudo apt install -y ufw fail2ban unattended-upgrades git curl

blyns@vps$ sudo ufw default deny incoming
blyns@vps$ sudo ufw default allow outgoing
blyns@vps$ sudo ufw allow OpenSSH
blyns@vps$ sudo ufw allow 80/tcp
blyns@vps$ sudo ufw allow 443/tcp
blyns@vps$ sudo ufw --force enable
blyns@vps$ sudo ufw status verbose        # expect 22, 80, 443 only

blyns@vps$ sudo systemctl enable --now fail2ban
blyns@vps$ sudo dpkg-reconfigure -plow unattended-upgrades   # answer Yes
```

MongoDB is **never** opened here. It is reachable only on the internal Docker
network; `ufw` is the second line of defence, not the first.

## 3. Docker

From Docker's own repository — Ubuntu's packaged version lags badly.

```bash
blyns@vps$ sudo install -m 0755 -d /etc/apt/keyrings
blyns@vps$ curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
             | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
blyns@vps$ sudo chmod a+r /etc/apt/keyrings/docker.gpg
blyns@vps$ echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
             | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
blyns@vps$ sudo apt update
blyns@vps$ sudo apt install -y docker-ce docker-ce-cli containerd.io \
             docker-buildx-plugin docker-compose-plugin
blyns@vps$ sudo usermod -aG docker blyns
```

Log out and back in so the group applies, then:

```bash
blyns@vps$ docker run --rm hello-world
```

## 4. Get the code

The repository is public, so this needs no credentials.

```bash
blyns@vps$ sudo mkdir -p /opt/blyns && sudo chown blyns:blyns /opt/blyns
blyns@vps$ git clone https://github.com/AdhamGamal3008/Blyns_ops.git /opt/blyns
blyns@vps$ cd /opt/blyns
```

Only the compose file, `deploy/`, and `scripts/` are used at runtime — the
application itself arrives as a prebuilt image.

## 5. GHCR — no login needed (verified 2026-08-17)

The published package is **public**, inheriting the repository's visibility, so
the server pulls anonymously and needs no token:

```bash
blyns@vps$ docker pull ghcr.io/adhamgamal3008/blyns-erp:v1.0.0
```

> **If the repository is ever made private, make the package private too** —
> otherwise it keeps serving an image containing the source. GitHub → Packages →
> `blyns-erp` → Package settings → Change visibility. At that point this step
> becomes `docker login ghcr.io -u AdhamGamal3008` with a `read:packages` token.

> **The image is `linux/amd64` only** — right for a Contabo VPS. It cannot be
> pulled on an Apple Silicon Mac; that is expected, not a fault. Build locally
> with `make build-image` if you need to run it on the Mac.

## 6. Secrets and configuration

```bash
blyns@vps$ cp .env.production.example .env.production
blyns@vps$ chmod 600 .env.production
```

Generate the four secrets **on the server** and write them straight in:

```bash
blyns@vps$ JWT=$(openssl rand -hex 32)
blyns@vps$ ROOTPW=$(openssl rand -hex 24)
blyns@vps$ APPPW=$(openssl rand -hex 24)

blyns@vps$ sed -i "s|^ERP_JWT_SECRET=.*|ERP_JWT_SECRET=$JWT|" .env.production
blyns@vps$ sed -i "s|^MONGO_ROOT_PASSWORD=.*|MONGO_ROOT_PASSWORD=$ROOTPW|" .env.production
blyns@vps$ sed -i "s|^MONGO_APP_PASSWORD=.*|MONGO_APP_PASSWORD=$APPPW|" .env.production
blyns@vps$ sed -i "s|^ERP_MONGO_URI=.*|ERP_MONGO_URI=\"mongodb://erpapp:$APPPW@mongo:27017/?replicaSet=rs0\&authSource=admin\"|" .env.production
blyns@vps$ unset JWT ROOTPW APPPW
```

Set the image to the tag you intend to run:

```bash
blyns@vps$ sed -i "s|^ERP_IMAGE=.*|ERP_IMAGE=ghcr.io/adhamgamal3008/blyns-erp:latest|" .env.production
```

Now check it by eye — `ERP_DOMAIN=blyns-eg.com`, CORS naming the real origins, the
Mongo URI **quoted** (the `&` is a shell metacharacter):

```bash
blyns@vps$ grep -E "ERP_DOMAIN|ERP_ENV|CORS|MONGO_URI|ERP_IMAGE" .env.production
```

Generate the replica-set keyfile:

```bash
blyns@vps$ ./scripts/init_mongo_keyfile.sh
blyns@vps$ sudo chown 999:999 deploy/mongo-keyfile      # mongod's uid; required
blyns@vps$ ls -l deploy/mongo-keyfile                   # expect -r-------- 999 999
```

## 7. DNS — do this BEFORE starting Caddy

In GoDaddy → **My Products → blyns-eg.com → DNS → Manage Zones**:

| Type | Name | Value | TTL |
|---|---|---|---|
| `A` | `@` | `<VPS_IP>` | 600 |
| `A` | `www` | `<VPS_IP>` | 600 |
| `AAAA` | `@` | `<VPS_IPv6>` *(only if you have one)* | 600 |
| `AAAA` | `www` | `<VPS_IPv6>` *(only if you have one)* | 600 |

**Delete GoDaddy's parking records first** — a fresh domain ships with an `A @`
pointing at their parking page and usually a `CNAME www`. A leftover `CNAME www`
silently wins over your `A www`, giving a working apex and a broken `www`.

Wait, then confirm from your Mac:

```bash
you@laptop$ dig +short blyns-eg.com
you@laptop$ dig +short www.blyns-eg.com
```

**Both must return the VPS IP before you continue.** Starting Caddy early fails
the ACME challenge, and Let's Encrypt allows only 5 failures per hostname per
hour.

## 8. Database first

```bash
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml \
             up -d mongo mongo-init
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml \
             logs mongo-init
```

Expect `replica set rs0 is PRIMARY`. Then wait for the health check:

```bash
blyns@vps$ docker inspect -f '{{.State.Health.Status}}' \
             "$(docker compose --env-file .env.production -f docker-compose.prod.yml ps -q mongo)"
```

It reports `healthy` only once a primary is elected, which is what the app needs.

> Container names are derived from the directory (`/opt/blyns` → `blyns-mongo-1`),
> so ask compose for the id rather than typing a name that changes if the path
> does. Shorthand used below: `DC="docker compose --env-file .env.production -f
> docker-compose.prod.yml"`.

## 9. Application

```bash
blyns@vps$ DC="docker compose --env-file .env.production -f docker-compose.prod.yml"
blyns@vps$ $DC pull app
blyns@vps$ $DC up -d app
blyns@vps$ docker inspect -f '{{.State.Health.Status}}' "$($DC ps -q app)"
```

Set the trusted-proxy range so the backend sees real client IPs rather than
Caddy's — without this every visitor shares one rate-limit bucket and IP rules
match the proxy:

```bash
# the network compose actually created for this project
blyns@vps$ NET=$(docker inspect "$($DC ps -q app)" \
             -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}')
blyns@vps$ docker network inspect "$NET" -f '{{(index .IPAM.Config 0).Subnet}}'
# put that value in ERP_IP_TRUSTED_PROXIES, e.g. ["172.18.0.0/16"], then:
blyns@vps$ $DC up -d app
```

Confirm it took effect — the access log must show visitor IPs, not one repeated
gateway address:

```bash
blyns@vps$ $DC logs app | grep -o '"client": "[^"]*"' | sort | uniq -c | tail -5
```

## 10. Seed and migrate

```bash
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml \
             exec -T app python scripts/seed_control_plane.py
```

> **The super-admin password is printed once and stored nowhere.** Copy it into
> your password manager now, and change it at first login.

```bash
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml \
             exec -T app python scripts/migrate.py
```

## 11. TLS

Only once §7's `dig` checks pass:

```bash
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml \
             up -d caddy
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml \
             logs -f caddy        # watch the certificate be issued, then Ctrl-C
```

## 12. Verify from the outside

From your Mac, not the server:

```bash
you@laptop$ curl -sI https://blyns-eg.com | head -3           # 200, valid cert
you@laptop$ curl -s https://blyns-eg.com/health               # status ok
you@laptop$ curl -s https://blyns-eg.com/ | grep -o "<title>[^<]*"
you@laptop$ curl -sI http://blyns-eg.com | grep -i location   # redirects to https
you@laptop$ nc -zv <VPS_IP> 27017                             # MUST refuse
```

Then in a browser: `https://blyns-eg.com` (landing), `/admin` (portal — log in and
change that password), `/app` (client).

## 13. Backups

```bash
blyns@vps$ ./scripts/backup_mongo.sh backup
blyns@vps$ ./scripts/backup_mongo.sh list
```

Schedule nightly at 03:15:

```bash
blyns@vps$ crontab -e
15 3 * * * cd /opt/blyns && ./scripts/backup_mongo.sh backup >> /var/log/blyns-backup.log 2>&1
```

A backup on the same disk does not survive the failure it exists for. Set
`BACKUP_ENCRYPT_TO` (a GPG recipient) and `BACKUP_REMOTE` (an rsync destination)
so a copy leaves the box encrypted — see `DEPLOYMENT_PLAN.md` §1a.

**Rehearse a restore before you need one.** A backup you have never restored is a
hypothesis:

```bash
blyns@vps$ ./scripts/backup_mongo.sh restore backups/<timestamp> erp_tenant_<slug>
```

---

## Routine operations

### Deploy a new version

```bash
blyns@vps$ cd /opt/blyns && git pull
blyns@vps$ sed -i "s|^ERP_IMAGE=.*|ERP_IMAGE=ghcr.io/adhamgamal3008/blyns-erp:sha-<commit>|" .env.production
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml pull app
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml up -d app
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml exec -T app python scripts/migrate.py
```

Cut a release first by tagging on your Mac — `git tag v1.0.0 && git push origin
v1.0.0` — which builds, smoke-tests and publishes the image.

### Roll back

Point `ERP_IMAGE` at the previous `sha-` tag and `up -d app`. This is why images
carry SHA tags: rollback is the exact bytes that worked, with no rebuild.

> Migrations are **not** rolled back. They are written to be idempotent and
> additive, so an older image runs against a newer database — but check the
> migration before rolling back across one.

### Logs, status, restart

```bash
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml ps
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml logs -f app
blyns@vps$ docker compose --env-file .env.production -f docker-compose.prod.yml restart app
```

### Rotate the JWT secret

Generate a new one, update `.env.production`, `up -d app`. **Every session is
invalidated — everyone is logged out.** Do it deliberately, not casually.

### Onboard a tenant

Through the admin portal at `https://blyns-eg.com/admin`. Provisioning creates the
tenant's own database and seeds every module; nothing is done by hand.

---

## If something is wrong

| Symptom | Likely cause |
|---|---|
| App container restarts in a loop | Config rejected at startup. `logs app` prints every violation at once — weak `ERP_JWT_SECRET`, localhost CORS, or a localhost Mongo URI. |
| App healthy, browser shows nothing | Caddy not up, or DNS not resolving. Check `logs caddy`. |
| Caddy cannot get a certificate | DNS not pointing here yet, or port 80 blocked. Confirm `dig` and `ufw status`. |
| `mongo-init` exits non-zero | Wrong credentials, or the keyfile is not owned by uid 999. |
| App cannot authenticate to Mongo | `MONGO_APP_PASSWORD` and the password inside `ERP_MONGO_URI` disagree. |
| Every request seems rate-limited | `ERP_IP_TRUSTED_PROXIES` unset — all users are sharing Caddy's bucket. |
| `docker compose` says a variable is not set | You omitted `--env-file .env.production`. |
