import { useEffect, useState } from "react";
import { api } from "../../shared/api";
import { Button, Card, ErrorNote, Field, Spinner } from "../../shared/ui";

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

  useEffect(() => {
    api<Profile>("/settings/company").then((r) => setProfile(r.data)).catch(setError);
  }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setError(null);
    setSaved(false);
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
    }
  }

  if (!profile && !error) return <Spinner />;
  return (
    <Card title="Company profile">
      <ErrorNote error={error} />
      {saved && <p className="muted">Saved.</p>}
      {profile && (
        <form onSubmit={save} style={{ maxWidth: 420 }}>
          <Field label="Name">
            <input value={profile.name ?? ""} disabled={!props.canWrite}
              onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
          </Field>
          <Field label="Legal name">
            <input value={profile.legal_name ?? ""} disabled={!props.canWrite}
              onChange={(e) => setProfile({ ...profile, legal_name: e.target.value })} />
          </Field>
          <Field label="Timezone">
            <input value={profile.timezone ?? ""} disabled={!props.canWrite}
              onChange={(e) => setProfile({ ...profile, timezone: e.target.value })} />
          </Field>
          <Field label="Currency (ISO 4217)">
            <input value={profile.currency ?? ""} maxLength={3} disabled={!props.canWrite}
              onChange={(e) => setProfile({ ...profile, currency: e.target.value.toUpperCase() })} />
          </Field>
          <Field label="Fiscal year start (MM-DD)">
            <input value={profile.fiscal_year_start ?? ""} pattern="\d{2}-\d{2}"
              disabled={!props.canWrite}
              onChange={(e) => setProfile({ ...profile, fiscal_year_start: e.target.value })} />
          </Field>
          {props.canWrite && <Button type="submit">Save</Button>}
        </form>
      )}
    </Card>
  );
}
