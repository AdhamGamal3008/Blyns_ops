#!/usr/bin/env bash
# Generate the MongoDB replica-set keyfile (docs/DEPLOYMENT_PLAN.md Phase C).
#
# A replica set running with --auth needs a shared secret its members authenticate
# to each other with. Even a SINGLE-node set requires one: mongod refuses to start
# with --replSet and --auth and no --keyFile.
#
# mongod is deliberately fussy about this file and fails with a bare
# "permissions on /etc/mongo/keyfile are too open" if it is wrong:
#   * mode must be 400 (or 600) — group/other readable is refused outright;
#   * it must be owned by the user mongod runs as, which in the official image is
#     uid 999. A bind mount keeps the HOST's ownership, so a file owned by your
#     login is rejected inside the container.
#
# Run once, on the server, before the first `docker compose up`:
#   ./scripts/init_mongo_keyfile.sh
#
# The keyfile is a SECRET: it is gitignored and must never be committed. Losing it
# is recoverable (regenerate and restart), but it must be identical across members
# if this ever grows beyond one node.

set -euo pipefail

KEYFILE="${1:-deploy/mongo-keyfile}"

if [[ -f "$KEYFILE" ]]; then
  echo "keyfile already exists at $KEYFILE — leaving it alone."
  echo "Delete it deliberately if you intend to rotate it (all members must match)."
  exit 0
fi

mkdir -p "$(dirname "$KEYFILE")"

# 756 bytes of base64 — comfortably inside mongod's 6..1024 character window.
openssl rand -base64 756 > "$KEYFILE"
chmod 400 "$KEYFILE"

# Match the uid mongod runs as inside the official image. Needs root on Linux;
# on Docker Desktop for macOS the VM maps ownership anyway, so a failure here is
# not fatal locally — but it IS fatal on the Linux server, so we say so loudly.
if chown 999:999 "$KEYFILE" 2>/dev/null; then
  echo "created $KEYFILE (mode 400, owned by uid 999 — mongod's user)"
else
  echo "created $KEYFILE (mode 400)"
  echo
  echo "NOTE: could not chown to 999:999 — you are probably not root."
  echo "On the Linux server this matters: mongod will refuse the keyfile unless it"
  echo "owns it. Fix with:"
  echo "    sudo chown 999:999 $KEYFILE"
  echo "On Docker Desktop for macOS you can ignore this — the VM maps ownership."
fi
