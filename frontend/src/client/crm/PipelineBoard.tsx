// Pipeline board (§3 `/crm/pipeline`): stage buckets with counts + summed
// amounts, and the deal list underneath. Stage moves go through
// PATCH /crm/deals/{id}/stage so the `lost_reason` rule is enforced server-side.

import { Plus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Badge,
  Banner,
  Button,
  CardHeader,
  DataState,
  errorText,
  Field,
  FormModal,
  Input,
  NativeSelect,
} from "../../shared/ui";
import type { CsvGrants } from "../../shared/csv/access";
import { DataTransfer } from "../../shared/csv/DataTransfer";
import styles from "./PipelineBoard.module.css";
import { companyCurrency } from "../../shared/currency";

interface StageBucket {
  stage: string;
  count: number;
  amount: number;
  is_terminal: boolean;
}

interface Pipeline {
  pipeline: string;
  name: string;
  stages: StageBucket[];
  open_value: number;
}

interface Deal {
  id: string;
  title: string;
  stage: string;
  amount: number;
  currency: string;
  expected_close_date?: string | null;
  lost_reason?: string | null;
}

export function money(n: number, _currency?: string): string {
  // Company currency only (see projects/types.ts money); the arg is ignored.
  return new Intl.NumberFormat(undefined, {
    style: "currency", currency: companyCurrency(), maximumFractionDigits: 0,
  }).format(n);
}

export function PipelineBoard(props: { canWrite: boolean; csv: CsvGrants; openNew?: boolean }) {
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [deals, setDeals] = useState<Deal[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [moving, setMoving] = useState<Deal | null>(null);
  const [creating, setCreating] = useState(Boolean(props.openNew));

  // scope the cards to the same pipeline the buckets count, so a column's
  // total can never disagree with the cards under it
  const load = useCallback(() => {
    api<Pipeline>("/crm/pipeline").then((r) => setPipeline(r.data)).catch(setError);
    api<Deal[]>("/crm/deals?page_size=100&pipeline=default")
      .then((r) => setDeals(r.data)).catch(setError);
  }, []);

  useEffect(load, [load]);

  async function move(deal: Deal, stage: string) {
    // `lost` needs a reason — collect it before calling (acceptance #2).
    if (stage === "lost") {
      setMoving(deal);
      return;
    }
    setError(null);
    try {
      await api(`/crm/deals/${deal.id}/stage`, { method: "PATCH", body: { stage } });
      load();
    } catch (err) {
      setError(err);
    }
  }

  const ready = pipeline && deals;

  return (
    <section>
      <CardHeader
        title="Pipeline"
        description={pipeline ? `${money(pipeline.open_value)} open` : "Deal flow by stage"}
        actions={
          <>
            <DataTransfer module="crm" entity="deals" csv={props.csv}
              onImported={load} />
            {props.canWrite && (
              <Button size="compact" onClick={() => setCreating(true)}>
                <Plus size={15} aria-hidden="true" />
                New deal
              </Button>
            )}
          </>
        }
      />

      {error != null && ready && (
        <Banner tone="danger" title="That action failed">{errorText(error)}</Banner>
      )}

      <DataState loading={!ready && !error} error={ready ? null : error} onRetry={load}>
        {ready && (
          <div className={styles.board}>
            {pipeline.stages.map((s) => {
              const cards = deals.filter((d) => d.stage === s.stage);
              return (
                <div
                  key={s.stage}
                  className={`${styles.col} ${s.is_terminal ? styles.terminal : ""}`}
                >
                  <div className={styles.colHead} data-testid="stage-head">
                    <b>{s.stage}</b>
                    <span className={styles.count}>{s.count}</span>
                  </div>
                  <div className={styles.colTotal} data-testid="stage-total">
                    {money(s.amount)}
                  </div>

                  {cards.length === 0 && <p className={styles.empty}>No deals</p>}

                  {cards.map((d) => (
                    <article key={d.id} className={styles.card} title={d.lost_reason ?? ""}>
                      <span className={styles.cardTitle}>{d.title}</span>
                      <span className={styles.cardAmount}>{money(d.amount, d.currency)}</span>
                      {props.canWrite && !s.is_terminal && (
                        <NativeSelect
                          data-testid="deal-stage"
                          selectSize="compact"
                          aria-label={`Move ${d.title} to another stage`}
                          value={d.stage}
                          onChange={(e) => move(d, e.target.value)}
                          options={pipeline.stages.map((o) => ({
                            value: o.stage,
                            label: o.stage,
                          }))}
                        />
                      )}
                      {s.is_terminal && (
                        <Badge tone={s.stage === "won" ? "success" : "danger"}>{s.stage}</Badge>
                      )}
                    </article>
                  ))}
                </div>
              );
            })}
          </div>
        )}
      </DataState>

      {moving && (
        <LostReasonModal deal={moving}
          onDone={(ok) => { setMoving(null); if (ok) load(); }} />
      )}
      <DealModal open={creating} onDone={(ok) => { setCreating(false); if (ok) load(); }} />
    </section>
  );
}

function LostReasonModal(props: { deal: Deal; onDone: (ok: boolean) => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api(`/crm/deals/${props.deal.id}/stage`, {
        method: "PATCH", body: { stage: "lost", lost_reason: reason },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onDone(false)}
      title={`Mark “${props.deal.title}” lost`}
      onSubmit={submit}
      error={error}
      errorTitle="Could not update the deal"
      busy={busy}
      destructive
      submitLabel="Mark lost"
    >
      <Field label="Reason" required>
        <Input value={reason} onChange={(e) => setReason(e.target.value)}
          required placeholder="e.g. price, timing, competitor" />
      </Field>
    </FormModal>
  );
}

function DealModal(props: { open: boolean; onDone: (ok: boolean) => void }) {
  const [title, setTitle] = useState("");
  const [amount, setAmount] = useState("0");
  const [close, setClose] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api("/crm/deals", {
        method: "POST",
        body: {
          title, amount: Number(amount),
          expected_close_date: close ? new Date(close).toISOString() : null,
        },
      });
      props.onDone(true);
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open={props.open}
      onOpenChange={(o) => !o && props.onDone(false)}
      title="New deal"
      onSubmit={submit}
      error={error}
      errorTitle="Could not create the deal"
      busy={busy}
      submitLabel="Create deal"
    >
      <Field label="Title" required>
        <Input value={title} onChange={(e) => setTitle(e.target.value)} required />
      </Field>
      <Field label="Amount">
        <Input type="number" min="0" value={amount}
          onChange={(e) => setAmount(e.target.value)} />
      </Field>
      <Field label="Expected close date">
        <Input type="date" value={close} onChange={(e) => setClose(e.target.value)} />
      </Field>
    </FormModal>
  );
}
