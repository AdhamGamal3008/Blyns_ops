// Create the least-privilege application user (docs/DEPLOYMENT_PLAN.md Phase C).
//
// Files in /docker-entrypoint-initdb.d run ONCE, on a genuinely empty data
// directory, against a TEMPORARY mongod the entrypoint starts for this purpose.
//
// That temporary server is deliberately started WITHOUT --replSet, which is why
// `rs.initiate()` cannot live here: it would either fail outright or configure
// nothing, and the real mongod would then come up with --replSet and no config.
// Initiating the replica set is the `mongo-init` service's job in
// docker-compose.prod.yml. Users created here are written to the admin database
// on disk, so they survive into the replica-set mongod.

var appUser = process.env.MONGO_APP_USER;
var appPassword = process.env.MONGO_APP_PASSWORD;

if (!appUser || !appPassword) {
  throw new Error(
    "MONGO_APP_USER / MONGO_APP_PASSWORD must be set — refusing to leave the " +
      "application without its own credentials"
  );
}

var admin = db.getSiblingDB("admin");

if (admin.getUser(appUser)) {
  print("app user " + appUser + " already exists — leaving it alone");
} else {
  // Deliberately NOT root: it may read and write its own databases and create
  // new ones — tenant provisioning creates a database per company, and their
  // names are not known ahead of time (CLAUDE.md rule 2) — but it is not an
  // administrator of the cluster and cannot manage users or the replica set.
  admin.createUser({
    user: appUser,
    pwd: appPassword,
    roles: [{ role: "readWriteAnyDatabase", db: "admin" }],
  });
  print("created application user " + appUser);
}
