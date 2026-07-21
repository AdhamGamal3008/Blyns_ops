// Company profile (§1.1) — the tenant's own identity and accounting defaults.

import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  DataState,
  errorText,
  Field,
  FormActions,
  FormGrid,
  Input,
  Stack,
} from "../../shared/ui";

interface Profile {
  name?: string;
  legal_name?: string;
  timezone?: string;
  currency?: string;
  fiscal_year_start?: string;
  contact?: { email?: string; phone?: string };
}

export function ProfileSection(props: { canWrite: boolean }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Profile>("/settings/company").then((r) => setProfile(r.data)).catch(setError);
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setError(null);
    setSaved(false);
    setBusy(true);
    try {
      const res = await api<Profile>("/settings/company", {
        method: "PATCH",
        body: {
          name: profile.name, legal_name: profile.legal_name,
          timezone: profile.timezone, currency: profile.currency,
          fiscal_year_start: profile.fiscal_year_start, contact: profile.contact,
        },
      });
      setProfile(res.data);
      setSaved(true);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <CardHeader title="Company profile" description="Identity and accounting defaults." />
      <DataState loading={!profile && !error} error={profile ? null : error}>
        {profile && (
          <Card>
            <form onSubmit={save}>
              <Stack gap={4}>
                {error != null && (
                  <Banner tone="danger" title="Could not save">{errorText(error)}</Banner>
                )}
                {saved && (
                  <Banner tone="success" onDismiss={() => setSaved(false)}>
                    Company profile saved.
                  </Banner>
                )}

                <FormGrid>
                  <Field label="Name">
                    <Input value={profile.name ?? ""} disabled={!props.canWrite}
                      onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
                  </Field>
                  <Field label="Legal name">
                    <Input value={profile.legal_name ?? ""} disabled={!props.canWrite}
                      onChange={(e) => setProfile({ ...profile, legal_name: e.target.value })} />
                  </Field>
                  <Field label="Timezone">
                    <Input value={profile.timezone ?? ""} disabled={!props.canWrite}
                      onChange={(e) => setProfile({ ...profile, timezone: e.target.value })} />
                  </Field>
                  <Field label="Currency" hint="ISO 4217, e.g. USD.">
                    <Input value={profile.currency ?? ""} maxLength={3} disabled={!props.canWrite}
                      onChange={(e) =>
                        setProfile({ ...profile, currency: e.target.value.toUpperCase() })} />
                  </Field>
                  <Field label="Fiscal year start" hint="MM-DD.">
                    <Input value={profile.fiscal_year_start ?? ""} pattern="\d{2}-\d{2}"
                      disabled={!props.canWrite}
                      onChange={(e) =>
                        setProfile({ ...profile, fiscal_year_start: e.target.value })} />
                  </Field>
                </FormGrid>

                {props.canWrite && (
                  <FormActions>
                    <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
                  </FormActions>
                )}
              </Stack>
            </form>
          </Card>
        )}
      </DataState>
    </section>
  );
}
