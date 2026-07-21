// Client login + the forced password reset flow (docs/AUTH_RBAC.md §4).

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { changePassword, clientLogin } from "../shared/auth";
import { Button, Card, ErrorNote, Field } from "../shared/legacy-ui";

export function ClientLogin() {
  const navigate = useNavigate();
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [mustReset, setMustReset] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submitLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await clientLogin(company, email, password);
      if (result.password_reset_required) {
        setMustReset(true); // stay here; force the change before proceeding
      } else {
        navigate("/app");
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await changePassword(password, newPassword);
      await clientLogin(company, email, newPassword); // re-login with new pw
      navigate("/app");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-box">
        <Card>
          <h1>Blyns ERP</h1>
          <p className="sub">
            {mustReset
              ? "Set a new password to continue (first login)."
              : "Sign in to your company workspace."}
          </p>
          <ErrorNote error={error} />
          {!mustReset ? (
            <form onSubmit={submitLogin}>
              <Field label="Company">
                <input value={company} onChange={(e) => setCompany(e.target.value)}
                  placeholder="acme" autoFocus required />
              </Field>
              <Field label="Email">
                <input type="email" value={email}
                  onChange={(e) => setEmail(e.target.value)} required />
              </Field>
              <Field label="Password">
                <input type="password" value={password}
                  onChange={(e) => setPassword(e.target.value)} required />
              </Field>
              <Button type="submit" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </Button>
            </form>
          ) : (
            <form onSubmit={submitReset}>
              <Field label="New password (min 8 chars)">
                <input type="password" value={newPassword} minLength={8}
                  onChange={(e) => setNewPassword(e.target.value)} autoFocus required />
              </Field>
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : "Set password & continue"}
              </Button>
            </form>
          )}
          <p className="sub" style={{ marginTop: 16 }}>
            Platform operator? <a href="/admin/login">Admin sign-in</a>
          </p>
        </Card>
      </div>
    </div>
  );
}
