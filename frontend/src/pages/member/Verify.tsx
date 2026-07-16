import { useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { useSession } from "../../context/SessionContext";

/**
 * Magic-link landing page. We deliberately do NOT verify the token on page load:
 * email security scanners (e.g. Microsoft 365 Safe Links) pre-open links with a
 * headless browser, which would consume our single-use token before the member
 * ever clicks. Requiring an explicit tap means the scanner's visit is harmless
 * and the real click succeeds.
 *
 * The tap is also de-duped with a ref, not just the `status` state: two fast taps
 * can both enter verify() before React re-renders and swaps the button out, which
 * fired the exchange twice — the first call consumed the token and the second
 * 401'd, so the member saw "invalid or expired" on a link that had just worked.
 * (The backend now also tolerates this within a grace window; this is the belt to
 * that suspenders — see auth.py::verify_magic_link.)
 */
export default function Verify() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"idle" | "verifying" | "error">(token ? "idle" : "error");
  const [error, setError] = useState(token ? "" : "This link is missing its token — please request a new one.");
  const { setMember } = useSession();
  const navigate = useNavigate();
  const inFlight = useRef(false);

  async function verify() {
    if (!token || inFlight.current) return;
    inFlight.current = true;
    setStatus("verifying");
    setError("");
    try {
      const res = await api.post<{ token: string; first_name: string }>("/api/auth/member/verify", { token });
      setMember({ token: res.token, firstName: res.first_name });
      // A secure-message notification link lands the member in the message center;
      // otherwise carry the outreach's target measure through to the check-in.
      const next = params.get("next");
      const focus = params.get("focus");
      if (next === "messages") navigate("/messages", { replace: true });
      else navigate(focus ? `/screening?focus=${focus}` : "/screening", { replace: true });
    } catch (err) {
      inFlight.current = false; // a genuine failure should still be retryable
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "This link is invalid or expired — please request a new one.");
    }
  }

  return (
    <div className="app-shell" style={{ paddingTop: 64 }}>
      <div className="card" style={{ textAlign: "center" }}>
        {status === "error" ? (
          <>
            <p className="error-text">{error}</p>
            {/* A dead link is a dead end without this — the member has no way back
                to request another, and no reason to think one would help. */}
            <button className="btn secondary" onClick={() => navigate("/")} style={{ width: "100%" }}>
              Request a new link
            </button>
          </>
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
