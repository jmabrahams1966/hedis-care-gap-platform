import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { useSession } from "../../context/SessionContext";

/**
 * Magic-link landing page. We deliberately do NOT verify the token on page load:
 * email security scanners (e.g. Microsoft 365 Safe Links) pre-open links with a
 * headless browser, which would consume our single-use token before the member
 * ever clicks. Requiring an explicit tap means the scanner's visit is harmless
 * and the real click succeeds.
 */
export default function Verify() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"idle" | "verifying" | "error">(token ? "idle" : "error");
  const [error, setError] = useState(token ? "" : "This link is missing its token — please request a new one.");
  const { setMember } = useSession();
  const navigate = useNavigate();

  async function verify() {
    if (!token) return;
    setStatus("verifying");
    setError("");
    try {
      const res = await api.post<{ token: string; first_name: string }>("/api/auth/member/verify", { token });
      setMember({ token: res.token, firstName: res.first_name });
      // Carry the outreach's target measure through so the check-in opens it first.
      const focus = params.get("focus");
      navigate(focus ? `/screening?focus=${focus}` : "/screening", { replace: true });
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "This link is invalid or expired — please request a new one.");
    }
  }

  return (
    <div className="app-shell" style={{ paddingTop: 64 }}>
      <div className="card" style={{ textAlign: "center" }}>
        {status === "error" ? (
          <p className="error-text" style={{ marginBottom: 0 }}>
            {error}
          </p>
        ) : status === "verifying" ? (
          <>
            <span className="spinner" style={{ marginBottom: 12 }} />
            <p className="muted" style={{ marginBottom: 0 }}>
              Opening your check-in…
            </p>
          </>
        ) : (
          <>
            <h2>You're almost there</h2>
            <p className="muted">Tap below to securely open your health check-in.</p>
            <button className="btn" onClick={verify} style={{ width: "100%" }}>
              Continue to my check-in
            </button>
          </>
        )}
      </div>
    </div>
  );
}
