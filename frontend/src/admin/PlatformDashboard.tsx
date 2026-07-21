// Platform dashboard (docs/ADMIN_PORTAL.md §4): host capacity, rate limits,
// storage, cross-tenant activity — snapshots + live host stats.

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../shared/api";
import type { PlatformDashboard as Dash } from "../shared/types";
import { formatBytes, timeAgo } from "../shared/format";
import { Badge, Button, Card, ErrorNote, Spinner } from "../shared/legacy-ui";

function Meter(props: { pct: number }) {
  const cls = props.pct > 90 ? "danger" : props.pct > 75 ? "warn" : "";
  return (
    <div className={`meter ${cls}`}>
      <div style={{ width: `${Math.min(props.pct, 100)}%` }} />
    </div>
  );
}

export function PlatformDashboard() {
  const [dash, setDash] = useState<Dash | null>(null);
  const [headline, setHeadline] = useState<Record<string, number> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Dash | Record<string, number>>("/admin/dashboard", { realm: "admin" })
      .then((res) => {
        if ("host" in res.data) setDash(res.data as Dash);
        else setHeadline(res.data as Record<string, number>); // VIEW level
      })
      .catch(setError);
  }, []);

  useEffect(load, [load]);

  async function collectNow() {
    setBusy(true);
    setError(null);
    try {
      await api("/admin/metrics/collect", { method: "POST", realm: "admin" });
      load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setError(new Error("Your role cannot trigger collection."));
      } else setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (error && !dash && !headline) return <ErrorNote error={error} />;
  if (!dash && !headline) return <Spinner />;

  if (headline && !dash) {
    return (
      <div className="kpi-grid">
        {Object.entries(headline).map(([k, v]) => (
          <Card key={k} className="kpi">
            <div className="kpi-label">{k.replaceAll("_", " ")}</div>
            <div className="kpi-value">
              {k.includes("storage") ? formatBytes(v) : v}
            </div>
          </Card>
        ))}
      </div>
    );
  }

  const d = dash!;
  return (
    <>
      <ErrorNote error={error} />
      <Card
        title="Server capacity (live)"
        actions={
          <Button variant="ghost" onClick={collectNow} disabled={busy}>
            {busy ? "Collecting…" : "Collect snapshots now"}
          </Button>
        }
      >
        <div className="host-grid">
          <div>
            <div className="kpi-label">CPU</div>
            <div className="kpi-value">{d.host.cpu_pct.toFixed(0)}%</div>
            <Meter pct={d.host.cpu_pct} />
          </div>
          <div>
            <div className="kpi-label">Memory</div>
            <div className="kpi-value">{d.host.memory.pct.toFixed(0)}%</div>
            <Meter pct={d.host.memory.pct} />
          </div>
          <div>
            <div className="kpi-label">Disk</div>
            <div className="kpi-value">{d.host.disk.pct.toFixed(0)}%</div>
            <Meter pct={d.host.disk.pct} />
          </div>
          <div>
            <div className="kpi-label">Load / uptime</div>
            <div className="kpi-value">{d.host.load_avg[0].toFixed(2)}</div>
            <span className="muted">
              up {Math.floor(d.host.process.uptime_sec / 60)}m ·{" "}
              {d.host.process.workers} worker(s)
            </span>
          </div>
        </div>
      </Card>

      <div className="two-col">
        <Card title="Rate limits / throughput">
          <div className="kpi-grid">
            <div>
              <div className="kpi-label">Requests (last min)</div>
              <div className="kpi-value">{d.rates.requests_last_min}</div>
            </div>
            <div>
              <div className="kpi-label">429s (last min)</div>
              <div className="kpi-value">{d.rates.rate_limited_last_min}</div>
            </div>
          </div>
          {d.rates.top_tenants.length > 0 && (
            <table className="table" style={{ marginTop: 10 }}>
              <thead><tr><th>Tenant</th><th>Requests</th><th>Share</th></tr></thead>
              <tbody>
                {d.rates.top_tenants.map((t) => (
                  <tr key={t.tenant}>
                    <td>{t.tenant}</td><td>{t.requests}</td><td>{t.share_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title={`Storage — total ${formatBytes(d.storage.total_storage)}`}>
          <table className="table">
            <thead>
              <tr><th>Tenant</th><th>Data</th><th>Storage</th><th>Objects</th></tr>
            </thead>
            <tbody>
              {d.storage.tenants.map((t) => (
                <tr key={t.tenant_id}>
                  <td>{t.slug ?? t.tenant_id}</td>
                  <td>{formatBytes(t.data_size)}</td>
                  <td>{formatBytes(t.storage_size)}</td>
                  <td>{t.objects}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>

      <Card title={`Company activity — ${d.activity.companies_active}/${d.activity.companies_total} active, ${d.activity.active_users_24h_total} users in 24h`}>
        <table className="table">
          <thead>
            <tr>
              <th>Company</th><th>Status</th><th>Seats</th>
              <th>Logins 24h</th><th>Last activity</th><th>Module usage (7d)</th>
            </tr>
          </thead>
          <tbody>
            {d.activity.per_company.map((c) => (
              <tr key={c.company_id}>
                <td><b>{c.name}</b> <span className="muted">({c.slug})</span></td>
                <td>
                  <Badge tone={c.status === "active" ? "ok" : "danger"}>
                    {c.status}
                  </Badge>
                </td>
                <td>{c.seats_used}/{c.seat_limit}</td>
                <td>{c.logins_24h}</td>
                <td className="muted">
                  {c.last_activity_at ? timeAgo(c.last_activity_at) : "—"}
                </td>
                <td className="muted">
                  {Object.entries(c.module_usage)
                    .map(([m, n]) => `${m}:${n}`).join("  ") || "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
