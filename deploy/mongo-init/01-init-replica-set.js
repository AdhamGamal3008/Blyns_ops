// Initiate the single-node replica set and create the least-privilege app user
// (docs/DEPLOYMENT_PLAN.md Phase C).
//
// Files in /docker-entrypoint-initdb.d run ONCE, on a genuinely empty data
// directory. They do not re-run against an existing volume, so this is safe to
// leave mounted forever — but it also means changing it later has no effect on a
// live deployment; do that by hand via `docker compose exec mongo mongosh`.

// 1. Replica set. `mongo` is the compose service name, which is how the app
//    container resolves this host on the internal network.
try {
  rs.status();
  print("replica set already initiated — leaving it alone");
} catch (e) {
  rs.initiate({
    _id: "rs0",
    members: [{ _id: 0, host: "mongo:27017" }],
  });
  print("replica set rs0 initiated");
}

// Wait for this node to become PRIMARY before creating users — a write against a
// node still in STARTUP is rejected.
var waited = 0;
while (!db.hello().isWritablePrimary && waited < 30000) {
  sleep(500);
  waited += 500;
}
if (!db.hello().isWritablePrimary) {
  throw new Error("node did not become primary within 30s — cannot create app user");
}

// 2. The application user. Deliberately NOT root: it may read and write its own
//    databases and create new ones (tenant provisioning does exactly that), but
//    it is not an administrator of the cluster.
//
//    readWriteAnyDatabase is required because tenant databases are created on
//    demand at onboarding and their names are not known ahead of time
//    (database-per-tenant, CLAUDE.md rule 2).
var appUser = process.env.MONGO_APP_USER;
var appPassword = process.env.MONGO_APP_PASSWORD;

if (!appUser || !appPassword) {
  throw new Error("MONGO_APP_USER / MONGO_APP_PASSWORD must be set");
}

var admin = db.getSiblingDB("admin");
if (admin.getUser(appUser)) {
  print("app user already exists — leaving it alone");
} else {
  admin.createUser({
    user: appUser,
    pwd: appPassword,
    roles: [{ role: "readWriteAnyDatabase", db: "admin" }],
  });
  print("created application user " + appUser);
}
