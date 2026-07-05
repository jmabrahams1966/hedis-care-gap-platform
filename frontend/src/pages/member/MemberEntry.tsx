import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../../lib/api";

export default function MemberEntry() {
  const [memberId, setMemberId] = useState("");
  const [dob, setDob] = useState("");
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post<{ sent: boolean; dev_token?: string }>("/api/auth/member/magic", {
        external_member_id: memberId,
        date_of_birth: dob,
      });
      setSent(true);
      if (res.dev_token) setDevToken(res.dev_token);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  if (sent) {
    return (
      <div className="app-shell">
        <div className="card">
          <h2>Check your phone or email</h2>
          <p>If we found a match, a secure one-time link was just sent to you. It expires in 30 minutes.</p>
          {devToken && (
            <div>
              <p style={{ color: "var(--muted)", fontSize: 13 }}>Dev mode — link normally sent by SMS/email:</p>
              <button className="btn" onClick={() => navigate(`/verify?token=${devToken}`)}>
                Continue (dev shortcut)
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <h2>Start your check-in</h2>
      <form className="card" onSubmit={onSubmit}>
        {error && <p className="error-text">{error}</p>}
        <label htmlFor="memberId">Member ID</label>
        <input id="memberId" value={memberId} onChange={(e) => setMemberId(e.target.value)} required />
        <label htmlFor="dob">Date of birth</label>
        <input id="dob" type="date" value={dob} onChange={(e) => setDob(e.target.value)} required />
        <button className="btn" type="submit" disabled={loading}>
          {loading ? "Sending..." : "Send me a link"}
        </button>
      </form>
    </div>
  );
}
