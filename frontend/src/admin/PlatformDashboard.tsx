// Platform dashboard (docs/ADMIN_PORTAL.md §4): host capacity, rate limits,
// storage, cross-tenant activity — snapshots + live host stats.

import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../shared/api";
import { formatBytes, timeAgo } from "../shared/format";
import { PageHeader } from "../shared/shell";
import type { PlatformDashboard as Dash } from "../shared/types";
import {
  Badge,
  Banner,
  Button,
  Card,
  CardHeader,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Grid,
  KpiCard,
  Meter,
  Split,
  Stack,
} from "../shared/ui";
import styles from "./PlatformDashboard.module.css";

type TenantStorage = Dash["storage"]["tenants"][number];
type CompanyActivity = Dash["activity"]["per_company"][number];
type TopTenant = Dash["rates"]["top_tenants"][number];

/** A capacity tile: headline number, then the bar as a secondary read. */
function CapacityTile(props: { label: string; pct: number; hint?: string }) {
  return (
    <Card className={styles.capacity}>
      <span className={styles.capLabel}>{props.label}</span>
      <span className={styles.capValue}>{props.pct.toFixed(0)}%</span>
      <Meter value={props.pct} label={`${props.label} utilisation`} />
      {props.hint && <span className={styles.capHint}>{props.hint}</span>}
    </Card>
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

  const ready = dash || headline;

  // VIEW-level roles get only the headline counters, not the host detail.
  if (headline && !dash) {
    return (
      <Stack>
        <PageHeader title="Platform" description="Headline counters for your access level" />
        <Grid min={200}>
          {Object.entries(headline).map(([k, v]) => (
            <KpiCard
              key={k}
              label={k.replaceAll("_", " ")}
              value={k.includes("storage") ? formatBytes(v) : v.toLocaleString()}
            />
          ))}
        </Grid>
      </Stack>
    );
  }

  const storageColumns: DataTableColumn<TenantStorage>[] = [
    { key: "tenant", header: "Tenant", sortable: true, accessor: (t) => <b>{t.slug ?? t.tenant_id}</b>, sortValue: (t) => t.slug ?? t.tenant_id },
    { key: "data_size", header: "Data", numeric: true, sortable: true, accessor: (t) => formatBytes(t.data_size), sortValue: (t) => t.data_size },
    { key: "storage_size", header: "Storage", numeric: true, sortable: true, accessor: (t) => formatBytes(t.storage_size), sortValue: (t) => t.storage_size },
    { key: "objects", header: "Objects", numeric: true, sortable: true },
  ];

  const rateColumns: DataTableColumn<TopTenant>[] = [
    { key: "tenant", header: "Tenant", sortable: true },
    { key: "requests", header: "Requests", numeric: true, sortable: true },
    { key: "share_pct", header: "Share", numeric: true, sortable: true, accessor: (t) => `${t.share_pct}%` },
  ];

  const companyColumns: DataTableColumn<CompanyActivity>[] = [
    {
      key: "name",
      header: "Company",
      sortable: true,
      accessor: (c) => (
        <>
          <b>{c.name}</b>
          <div>{c.slug}</div>
        </>
      ),
      sortValue: (c) => c.name,
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      accessor: (c) => (
        <Badge tone={c.status === "active" ? "success" : "danger"}>{c.status}</Badge>
      ),
      sortValue: (c) => c.status,
    },
    {
      key: "seats",
      header: "Seats",
      numeric: true,
      sortable: true,
      sortValue: (c) => (c.seat_limit ? c.seats_used / c.seat_limit : 0),
      accessor: (c) => (
        <div className={styles.seats}>
          <span>{c.seats_used}/{c.seat_limit}</span>
          <Meter
            value={c.seats_used}
            max={c.seat_limit || 1}
            label={`Seats used at ${c.name}`}
          />
        </div>
      ),
    },
    { key: "logins_24h", header: "Logins 24h", numeric: true, sortable: true },
    {
      key: "last_activity_at",
      header: "Last activity",
      sortable: true,
      accessor: (c) => (c.last_activity_at ? timeAgo(c.last_activity_at) : "—"),
      sortValue: (c) => c.last_activity_at ?? "",
    },
    {
      key: "module_usage",
      header: "Module usage (7d)",
      accessor: (c) =>
        Object.entries(c.module_usage).map(([m, n]) => `${m}:${n}`).join("  ") || "—",
    },
  ];

  return (
    <DataState loading={!ready && !error} error={ready ? null : error} onRetry={load}>
      {dash && (
        <Stack>
          <PageHeader
            title="Platform"
            description="Host capacity, throughput, storage, and cross-tenant activity"
            actions={
              <Button variant="secondary" onClick={collectNow} disabled={busy}>
                <RefreshCw size={16} aria-hidden="true" />
                {busy ? "Collecting…" : "Collect snapshots"}
              </Button>
            }
          />

          {error != null && (
            <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
          )}

          <Grid min={200}>
            <CapacityTile label="CPU" pct={dash.host.cpu_pct} />
            <CapacityTile label="Memory" pct={dash.host.memory.pct} />
            <CapacityTile label="Disk" pct={dash.host.disk.pct} />
            <Card className={styles.capacity}>
              <span className={styles.capLabel}>Load / uptime</span>
              <span className={styles.capValue}>{dash.host.load_avg[0].toFixed(2)}</span>
              <span className={styles.capHint}>
                up {Math.floor(dash.host.process.uptime_sec / 60)}m ·{" "}
                {dash.host.process.workers} worker(s)
              </span>
            </Card>
          </Grid>

          <Split asideWidth={420}>
            <section>
              <CardHeader
                title="Storage"
                description={`${formatBytes(dash.storage.total_storage)} across all tenants`}
              />
              <DataState isEmpty={dash.storage.tenants.length === 0} emptyTitle="No tenant storage yet">
                <DataTable
                  data={dash.storage.tenants}
                  columns={storageColumns}
                  getRowId={(t) => t.tenant_id}
                  searchable={false}
                  pageSize={8}
                />
              </DataState>
            </section>

            <section>
              <CardHeader title="Throughput" description="Rate limiting over the last minute" />
              <Stack gap={4}>
                <Grid min={150}>
                  <KpiCard label="Requests / min" value={dash.rates.requests_last_min} />
                  <KpiCard label="429s / min" value={dash.rates.rate_limited_last_min} />
                </Grid>
                {dash.rates.top_tenants.length > 0 && (
                  <DataTable
                    data={dash.rates.top_tenants}
                    columns={rateColumns}
                    getRowId={(t) => t.tenant}
                    searchable={false}
                    pageSize={5}
                  />
                )}
              </Stack>
            </section>
          </Split>

          <section>
            <CardHeader
              title="Company activity"
              description={`${dash.activity.companies_active} of ${dash.activity.companies_total} active · ${dash.activity.active_users_24h_total} users in the last 24h`}
            />
            <DataState
              isEmpty={dash.activity.per_company.length === 0}
              emptyTitle="No companies onboarded yet"
            >
              <DataTable
                data={dash.activity.per_company}
                columns={companyColumns}
                getRowId={(c) => c.company_id}
                searchPlaceholder="Search companies…"
              />
            </DataState>
          </section>
        </Stack>
      )}
    </DataState>
  );
}
