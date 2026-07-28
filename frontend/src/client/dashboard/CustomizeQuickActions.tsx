// "Customize quick actions" (Phase 2): pin the actions you use most to the
// front, or hide the ones you never touch. The list is every action you're
// permitted to use (including ones you've hidden, so they can be brought back);
// the server re-checks the permission gate on save.

import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import type { CustomizableQuickAction } from "../../shared/types";
import { FormModal, NativeSelect, Spinner, Stack } from "../../shared/ui";
import styles from "./CustomizeQuickActions.module.css";

type Setting = "pinned" | "default" | "hidden";

const settingOf = (a: CustomizableQuickAction): Setting =>
  a.pinned ? "pinned" : a.hidden ? "hidden" : "default";

const OPTIONS = [
  { value: "pinned", label: "Pinned" },
  { value: "default", label: "Default" },
  { value: "hidden", label: "Hidden" },
];

export function CustomizeQuickActions(props: { onClose: () => void; onSaved: () => void }) {
  const [rows, setRows] = useState<CustomizableQuickAction[] | null>(null);
  const [choice, setChoice] = useState<Record<string, Setting>>({});
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<CustomizableQuickAction[]>("/dashboard/quick-actions/prefs")
      .then((res) => {
        setRows(res.data);
        setChoice(Object.fromEntries(res.data.map((a) => [a.key, settingOf(a)])));
      })
      .catch(setError);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    // `pinned` order is the on-screen (curated) order — that is the inline order.
    const list = rows ?? [];
    const pinned = list.filter((a) => choice[a.key] === "pinned").map((a) => a.key);
    const hidden = list.filter((a) => choice[a.key] === "hidden").map((a) => a.key);
    try {
      await api("/dashboard/quick-actions/prefs", {
        method: "PUT",
        body: { pinned, hidden },
      });
      props.onSaved();
    } catch (err) {
      setError(err);
      setBusy(false);
    }
  }

  return (
    <FormModal
      open
      onOpenChange={(o) => !o && props.onClose()}
      title="Customize quick actions"
      description="Pin the actions you use most to the front, or hide the ones you don’t."
      onSubmit={submit}
      error={error}
      errorTitle="Could not save your changes"
      busy={busy}
      submitLabel="Save"
    >
      {rows == null ? (
        <Spinner />
      ) : (
        <Stack gap={2}>
          {rows.map((a) => (
            <div key={a.key} className={styles.row}>
              <span>{a.label}</span>
              <NativeSelect
                selectSize="compact"
                aria-label={`${a.label} placement`}
                value={choice[a.key] ?? "default"}
                onChange={(e) =>
                  setChoice((c) => ({ ...c, [a.key]: e.target.value as Setting }))
                }
                options={OPTIONS}
              />
            </div>
          ))}
        </Stack>
      )}
    </FormModal>
  );
}
