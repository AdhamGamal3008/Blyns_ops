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
  Row,
  Stack,
} from "../../shared/ui";

function readAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

interface Profile {
  name?: string;
  legal_name?: string;
  timezone?: string;
  currency?: string;
  fiscal_year_start?: string;
  contact?: { email?: string; phone?: string };
  logo_ref?: string | null;
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
          logo_ref: profile.logo_ref,
        },
      });
      setProfile(res.data);
      setSaved(true);
      // keep the sidebar brand in sync without a reload
      window.dispatchEvent(new CustomEvent("blyns:company-logo",
        { detail: res.data.logo_ref ?? null }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onLogoFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";  // allow re-picking the same file after a rejection
    if (!file || !profile) return;
    if (!file.type.startsWith("image/")) {
      setError(new Error("Please choose an image file."));
      return;
    }
    if (file.size > 256 * 1024) {
      setError(new Error("That image is too large — please choose one under 256 KB."));
      return;
    }
    setError(null);
    setSaved(false);
    setProfile({ ...profile, logo_ref: await readAsDataURL(file) });
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

                <Field label="Logo" hint="Shown in the sidebar. PNG, JPG or SVG, up to 256 KB.">
                  <Stack gap={2}>
                    {profile.logo_ref && (
                      <img src={profile.logo_ref} alt="Company logo"
                        style={{ height: 48, maxWidth: 180, objectFit: "contain",
                          borderRadius: "var(--r-md)" }} />
                    )}
                    {props.canWrite && (
                      <Row gap={2}>
                        <input type="file" accept="image/*" onChange={onLogoFile}
                          aria-label="Upload company logo" />
                        {profile.logo_ref && (
                          <Button type="button" variant="ghost" size="compact"
                            onClick={() => { setSaved(false); setProfile({ ...profile, logo_ref: null }); }}>
                            Remove
                          </Button>
                        )}
                      </Row>
                    )}
                  </Stack>
                </Field>

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
