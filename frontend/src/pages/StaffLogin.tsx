import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useSession } from "../context/SessionContext";

interface LoginResponse {
  token?: string;
  role?: "super_admin" | "payer_admin" | "care_manager";
  name?: string;
  tenant_id?: string | null;
  mfa_required?: boolean;
  mfa_token?: string;
}

export default function StaffLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const { setStaff } = useSession();
  const navigate = useNavigate();

  function completeLogin(res: LoginResponse) {
    setStaff({ token: res.token!, role: res.role!, name: res.name!, tenantId: res.tenant_id ?? null });
    navigate(res.role === "super_admin" ? "/superadmin" : "/queue");
  }

  async function onSubmitPassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post<LoginResponse>("/api/auth/staff/login", { email, password });
      if (res.mfa_required && res.mfa_token) {
        setMfaToken(res.mfa_token); // second factor needed
      } else {
        completeLogin(res);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  async function onSubmitCode(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post<LoginResponse>("/api/auth/staff/mfa/verify", { mfa_token: mfaToken, code });
      completeLogin(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Verification failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell" style={{ maxWidth: 400, paddingTop: 64 }}>
      <div className="stack" style={{ alignItems: "center", marginBottom: 20 }}>
        <span className="brand__mark" aria-hidden="true">
          +
        </span>
        <strong>HEDIS Care Gap</strong>
      </div>

      {mfaToken === null ? (
        <>
          <h2>Staff sign in</h2>
          <form className="card" onSubmit={onSubmitPassword}>
            {error && <p className="error-text">{error}</p>}
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <button className="btn" type="submit" disabled={loading} style={{ width: "100%" }}>
              {loading ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </>
      ) : (
        <>
          <h2>Two-factor verification</h2>
          <form className="card" onSubmit={onSubmitCode}>
            {error && <p className="error-text">{error}</p>}
            <p className="muted" style={{ fontSize: 14 }}>
              Enter the 6-digit code from your authenticator app.
            </p>
            <label htmlFor="code">Authentication code</label>
            <input
              id="code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              autoFocus
              required
            />
            <button className="btn" type="submit" disabled={loading || code.length !== 6} style={{ width: "100%" }}>
              {loading ? "Verifying…" : "Verify"}
            </button>
            <button
              type="button"
              className="btn secondary sm"
              style={{ width: "100%", marginTop: 8 }}
              onClick={() => {
                setMfaToken(null);
                setCode("");
                setError("");
              }}
            >
              ← Back
            </button>
          </form>
        </>
      )}

      <Link to="/" className="muted" style={{ fontSize: 13, textDecoration: "none" }}>
        ← Back home
      </Link>
    </div>
  );
}
