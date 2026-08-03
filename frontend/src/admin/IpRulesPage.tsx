// IP access control panel (docs/IP_ACCESS_CONTROL_PLAN.md §2-F): two lists
// (deny / allow), an add-rule form with a "this would block your current IP"
// guard, and the IP checker — the lockout-preventer admins consult before writing.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../shared/api";
import { PageHeader } from "../shared/shell";
import type { IpRule, IpTestResult, IpWhoami } from "../shared/types";
import {
  Badge,
  Banner,
  Button,
  Card,
  DataState,
  DataTable,
  type DataTableColumn,
  errorText,
  Field,
  FormModal,
  Input,
  NativeSelect,
  Row,
  Stack,
  Switch,
} from "../shared/ui";
import styles from "./IpRulesPage.module.css";
import { wouldBlockSelf } from "./ipMatch";

const MATCH_LABEL: Record<IpRule["match_type"], string> = {
  ip: "IP",
  cidr: "CIDR",
  country: "Country",
};

const KIND_OPTIONS = [
  { value: "deny", label: "Deny" },
  { value: "allow", label: "Allow" },
];
const MATCH_OPTIONS = [
  { value: "ip", label: "IP address" },
  { value: "cidr", label: "CIDR range" },
  { value: "country", label: "Country code" },
];
const VALUE_HINT: Record<IpRule["match_type"], { placeholder: string; hint: string }> = {
  ip: { placeholder: "203.0.113.5", hint: "A single IPv4 or IPv6 address." },
  cidr: { placeholder: "203.0.113.0/24", hint: "A CIDR range, e.g. 10.0.0.0/8." },
  country: { placeholder: "KP", hint: "ISO 3166-1 alpha-2 country code." },
};

export function IpRulesPage() {
  const [rules, setRules] = useState<IpRule[] | null>(null);
  const [whoami, setWhoami] = useState<IpWhoami | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [showAdd, setShowAdd] = useState(false);

  const load = useCallback(() => {
    api<IpRule[]>("/admin/ip-rules?page_size=100", { realm: "admin" })
      .then((res) => setRules(res.data))
      .catch(setError);
  }, []);

  useEffect(load, [load]);
  useEffect(() => {
    // Best-effort: the "would block you" guard degrades to off if this fails.
    api<IpWhoami>("/admin/ip-rules/whoami", { realm: "admin" })
      .then((res) => setWhoami(res.data))
      .catch(() => undefined);
  }, []);

  async function toggle(rule: IpRule) {
    setError(null);
    try {
      await api(`/admin/ip-rules/${rule.id}`, {
        method: "PATCH", body: { enabled: !rule.enabled }, realm: "admin",
      });
      load();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(rule: IpRule) {
    setError(null);
    try {
      await api(`/admin/ip-rules/${rule.id}`, { method: "DELETE", realm: "admin" });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const deny = (rules ?? []).filter((r) => r.kind === "deny");
  const allow = (rules ?? []).filter((r) => r.kind === "allow");

  return (
    <Stack>
      <PageHeader
        title="IP access control"
        description="Platform-wide allow / deny rules, enforced ahead of the rate limiter."
        actions={
          <Button onClick={() => setShowAdd(true)}>
            <Plus size={16} aria-hidden="true" />
            Add rule
          </Button>
        }
      />

      {error != null && rules != null && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <IpChecker />

      <DataState
        loading={!rules && !error}
        error={rules ? null : error}
        onRetry={load}
      >
        <Stack gap={4}>
          <RuleList
            title="Denylist"
            subtitle="Blocked IPs, ranges, and countries. Allowlist rules always win."
            rules={deny}
            onToggle={toggle}
            onRemove={remove}
          />
          <RuleList
            title="Allowlist"
            subtitle="Always allowed — the operator's escape hatch, immune to any deny."
            rules={allow}
            onToggle={toggle}
            onRemove={remove}
          />
        </Stack>
      </DataState>

      {showAdd && (
        <AddRuleModal
          whoami={whoami}
          onClose={(created) => {
            setShowAdd(false);
            if (created) load();
          }}
        />
      )}
    </Stack>
  );
}

function RuleList(props: {
  title: string;
  subtitle: string;
  rules: IpRule[];
  onToggle: (r: IpRule) => void;
  onRemove: (r: IpRule) => void;
}) {
  const { title, subtitle, rules } = props;
  const columns: DataTableColumn<IpRule>[] = [
    {
      key: "value",
      header: "Value",
      accessor: (r) => <code className={styles.value}>{r.value}</code>,
    },
    {
      key: "match_type",
      header: "Type",
      accessor: (r) => <Badge tone="neutral">{MATCH_LABEL[r.match_type]}</Badge>,
    },
    {
      key: "reason",
      header: "Reason",
      accessor: (r) =>
        r.reason ? <span>{r.reason}</span> : <span className={styles.muted}>—</span>,
    },
    {
      key: "source",
      header: "Source",
      accessor: (r) => (
        <Badge tone={r.source === "seed" ? "info" : "neutral"}>{r.source}</Badge>
      ),
    },
    {
      key: "enabled",
      header: "Enabled",
      accessor: (r) => (
        <Switch
          checked={r.enabled}
          onCheckedChange={() => props.onToggle(r)}
          aria-label={`${r.enabled ? "Disable" : "Enable"} rule ${r.value}`}
        />
      ),
    },
    {
      key: "actions",
      header: "",
      accessor: (r) => (
        <Button
          variant="danger"
          size="compact"
          onClick={() => props.onRemove(r)}
          aria-label={`Delete rule ${r.value}`}
        >
          Delete
        </Button>
      ),
    },
  ];

  return (
    <Card>
      <Stack gap={3}>
        <div>
          <Row gap={2} className={styles.titleRow}>
            <b>{title}</b>
            <Badge tone="neutral">{rules.length}</Badge>
          </Row>
          <div className={styles.subtitle}>{subtitle}</div>
        </div>
        {rules.length === 0 ? (
          <span className={styles.muted}>No {title.toLowerCase()} rules yet.</span>
        ) : (
          <DataTable
            data={rules}
            columns={columns}
            getRowId={(r) => r.id}
            searchable={rules.length > 8}
          />
        )}
      </Stack>
    </Card>
  );
}

function IpChecker() {
  const [ip, setIp] = useState("");
  const [result, setResult] = useState<IpTestResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function check(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    setBusy(true);
    try {
      const res = await api<IpTestResult>("/admin/ip-rules/test", {
        method: "POST", body: { ip: ip.trim() }, realm: "admin",
      });
      setResult(res.data);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={check}>
        <Stack gap={3}>
          <div>
            <b>Check an IP</b>
            <div className={styles.subtitle}>
              Would this address be allowed right now, and by which rule?
            </div>
          </div>
          <Row gap={2} className={styles.checkerRow}>
            <Field label="IP address" className={styles.grow}>
              <Input
                value={ip}
                onChange={(e) => setIp(e.target.value)}
                placeholder="203.0.113.5"
                aria-label="IP address to check"
              />
            </Field>
            <Button type="submit" disabled={!ip.trim() || busy}>Check</Button>
          </Row>
          {error != null && <Banner tone="danger">{errorText(error)}</Banner>}
          {result != null && (
            <Banner
              tone={result.allowed ? "success" : "danger"}
              title={result.allowed ? "Allowed" : "Blocked"}
            >
              {describeVerdict(result)}
            </Banner>
          )}
        </Stack>
      </form>
    </Card>
  );
}

function describeVerdict(r: IpTestResult): string {
  const where = r.country ? ` (geolocated to ${r.country})` : "";
  if (r.matched_rule) {
    const m = r.matched_rule;
    const by = `${m.kind} rule on ${MATCH_LABEL[m.match_type as IpRule["match_type"]] ?? m.match_type} ${m.value}`;
    return `${r.ip}${where} matches a ${by}.`;
  }
  return `${r.ip}${where} matches no rule — allowed by the default-allow posture.`;
}

function AddRuleModal(props: {
  whoami: IpWhoami | null;
  onClose: (created: boolean) => void;
}) {
  const [kind, setKind] = useState<IpRule["kind"]>("deny");
  const [matchType, setMatchType] = useState<IpRule["match_type"]>("ip");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const blocksSelf =
    props.whoami != null &&
    wouldBlockSelf(props.whoami.ip, props.whoami.country, kind, matchType, value);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/admin/ip-rules", {
        method: "POST", realm: "admin",
        body: {
          kind, match_type: matchType, value: value.trim(),
          reason: reason.trim() || null, enabled,
        },
      });
      props.onClose(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  const field = VALUE_HINT[matchType];

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onClose(false)}
      title="Add IP rule"
      description="Allowlist rules always win over the denylist."
      onSubmit={submit}
      error={error}
      errorTitle="Could not add the rule"
      busy={busy}
      submitDisabled={!value.trim()}
      submitLabel="Add rule"
      destructive={kind === "deny"}
    >
      <Field label="Action" required>
        <NativeSelect
          value={kind}
          onChange={(e) => setKind(e.target.value as IpRule["kind"])}
          options={KIND_OPTIONS}
          aria-label="Action"
        />
      </Field>
      <Field label="Match type" required>
        <NativeSelect
          value={matchType}
          onChange={(e) => setMatchType(e.target.value as IpRule["match_type"])}
          options={MATCH_OPTIONS}
          aria-label="Match type"
        />
      </Field>
      <Field label="Value" required hint={field.hint}>
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={field.placeholder}
          autoFocus
          required
        />
      </Field>
      <Field label="Reason">
        <Input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. office network"
        />
      </Field>
      <Switch
        label="Enabled"
        checked={enabled}
        onCheckedChange={(c) => setEnabled(c === true)}
      />
      {blocksSelf && props.whoami && (
        <Banner tone="warning" title="This would block your current IP">
          The server sees you at {props.whoami.ip}
          {props.whoami.country ? ` (${props.whoami.country})` : ""}. Add an allow
          rule for your address first, or you may lock yourself out.
        </Banner>
      )}
    </FormModal>
  );
}
