// Platform operator sign-in — a separate realm from the client workspace
// (docs/AUTH_RBAC.md §4): different pool, different token audience.

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminLogin } from "../shared/auth";
import { LoginLayout } from "../shared/login/LoginLayout";
import { Button, Field, Input, Stack } from "../shared/ui";

export function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await adminLogin(email, password);
      navigate("/admin");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <LoginLayout
      realm="Platform operator"
      lede="Sign in to the control plane."
      error={error}
      footer={<>Company employee? <a href="/login">Workspace sign-in</a></>}
    >
      <form onSubmit={submit}>
        <Stack gap={4}>
          <Field label="Email">
            <Input type="email" value={email} autoFocus required
              onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label="Password">
            <Input type="password" value={password} required
              onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" fullWidth disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </Stack>
      </form>
    </LoginLayout>
  );
}
