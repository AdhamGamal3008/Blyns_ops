// Client login + the forced password reset flow (docs/AUTH_RBAC.md §4).

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { changePassword, clientLogin } from "../shared/auth";
import { LoginLayout } from "../shared/login/LoginLayout";
import { Button, Field, Input, Stack } from "../shared/ui";

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
    <LoginLayout
      realm="Company workspace"
      lede={
        mustReset
          ? "Set a new password to continue — this is your first sign-in."
          : "Sign in to your company workspace."
      }
      error={error}
      footer={<>Platform operator? <a href="/admin/login">Admin sign-in</a></>}
    >
      {!mustReset ? (
        <form onSubmit={submitLogin}>
          <Stack gap={4}>
            <Field label="Company">
              <Input value={company} onChange={(e) => setCompany(e.target.value)}
                placeholder="acme" autoFocus required />
            </Field>
            <Field label="Email">
              <Input type="email" value={email}
                onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label="Password">
              <Input type="password" value={password}
                onChange={(e) => setPassword(e.target.value)} required />
            </Field>
            <Button type="submit" fullWidth disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </Stack>
        </form>
      ) : (
        <form onSubmit={submitReset}>
          <Stack gap={4}>
            <Field label="New password" hint="At least 8 characters.">
              <Input type="password" value={newPassword} minLength={8}
                onChange={(e) => setNewPassword(e.target.value)} autoFocus required />
            </Field>
            <Button type="submit" fullWidth disabled={busy}>
              {busy ? "Saving…" : "Set password & continue"}
            </Button>
          </Stack>
        </form>
      )}
    </LoginLayout>
  );
}
