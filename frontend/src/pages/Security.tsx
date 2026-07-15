import { useEffect, useState } from "react";
import { useSession } from "../context/SessionContext";
import { api, ApiError } from "../lib/api";

interface EnrollResponse {
  secret: string;
  otpauth_uri: string;
}

/** Group a base32 secret into 4-char blocks so it's readable when typed by hand
 * into an authenticator app. */
function formatSecret(secret: string): string {
  return (secret.match(/.{1,4}/g) ?? [secret]).join(" ");
}

export default function Security() {
  const { staff } = useSession();
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [enroll, setEnroll] = useState<EnrollResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function loadStatus() {
    api.get<{ mfa_enabled: boolean }>("/api/auth/staff/mfa/status", staff?.token).then((r) => setEnabled(r.mfa_enabled));
  }
  useEffect(loadStatus, [staff]);

  async function startEnroll() {
    setError("");
    setBusy(true);
    try {
      setEnroll(await api.post<EnrollResponse>("/api/auth/staff/mfa/enroll", {}, staff?.token));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start enrollment");
    } finally {
      setBusy(false);
    }
  }

  async function confirmEnroll() {
    setError("");
    setBusy(true);
    try {
      await api.post("/api/auth/staff/mfa/confirm", { code }, staff?.token);
      setEnroll(null);
      setCode("");
      loadStatus();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not confirm");
    } finally {
      setBusy(false);
    }
  }

  async function disable() {
    setError("");
    setBusy(true);
    try {
      await api.post("/api/auth/staff/mfa/disable", { code }, staff?.token);
      setCode("");
      loadStatus();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not disable");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Security</h1>
        <p>Two-factor authentication (TOTP) for your staff account.</p>
      </div>

      {error && <p className="error-text">{error}</p>}

      <div className="card">
        <div className="stack" style={{ alignItems: "center", justifyContent: "space-between" }}>
          <strong>Two-factor authentication</strong>
          {enabled === null ? (
            <span className="spinner" />
          ) : enabled ? (
            <span className="badge done">Enabled</span>
          ) : (
            <span className="badge open">Disabled</span>
          )}
        </div>
      </div>

      {/* Enable flow */}
      {enabled === false && !enroll && (
        <div className="card">
          <p>
            Protect your account with an authenticator app (Google Authenticator, Authy, 1Password, etc.). You'll enter
            a 6-digit code each time you sign in.
          </p>
          <button className="btn" onClick={startEnroll} disabled={busy}>
            {busy ? "Starting…" : "Enable two-factor"}
          </button>
        </div>
      )}

      {enabled === false && enroll && (
        <div className="card">
          <p>
            <strong>Step 1.</strong> In your authenticator app, add an account and enter this setup key (or open the
            link on your phone):
          </p>
          <p style={{ fontFamily: "monospace", fontSize: 18, letterSpacing: 1, wordBreak: "break-all" }}>
            {formatSecret(enroll.secret)}
          </p>
          <p className="muted" style={{ fontSize: 13 }}>
            <a href={enroll.otpauth_uri}>Open in authenticator app ↗</a>
          </p>
          <p style={{ marginTop: 16 }}>
            <strong>Step 2.</strong> Enter the 6-digit code it shows to confirm:
          </p>
          <input
            inputMode="numeric"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="123456"
          />
          <button className="btn" onClick={confirmEnroll} disabled={busy || code.length !== 6}>
            {busy ? "Confirming…" : "Confirm & enable"}
          </button>
        </div>
      )}

      {/* Disable flow */}
      {enabled === true && (
        <div className="card">
          <p>Two-factor is on. To turn it off, confirm with a current code from your authenticator app.</p>
          <input
            inputMode="numeric"
            maxLength={6}
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            placeholder="123456"
          />
          <button className="btn danger" onClick={disable} disabled={busy || code.length !== 6}>
            {busy ? "Disabling…" : "Disable two-factor"}
          </button>
        </div>
      )}
    </>
  );
}
