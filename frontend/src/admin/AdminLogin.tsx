import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminLogin } from "../shared/auth";
import { Button, Card, ErrorNote, Field } from "../shared/ui";

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
    <div className="login-wrap">
      <div className="login-box">
        <Card>
          <h1>Blyns ERP — Admin</h1>
          <p className="sub">Platform operator sign-in (separate realm).</p>
          <ErrorNote error={error} />
          <form onSubmit={submit}>
            <Field label="Email">
              <input type="email" value={email} autoFocus required
                onChange={(e) => setEmail(e.target.value)} />
            </Field>
            <Field label="Password">
              <input type="password" value={password} required
                onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <Button type="submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
          <p className="sub" style={{ marginTop: 16 }}>
            Company employee? <a href="/login">Workspace sign-in</a>
          </p>
        </Card>
      </div>
    </div>
  );
}
