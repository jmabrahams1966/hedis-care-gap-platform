import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="app-shell">
      <div className="stack" style={{ alignItems: "center", marginBottom: 16 }}>
        <span className="brand__mark" aria-hidden="true">
          +
        </span>
        <span className="muted" style={{ fontWeight: 700, letterSpacing: "0.02em" }}>
          HEDIS CARE GAP PLATFORM
        </span>
      </div>
      <h1>Close care gaps before they cost you.</h1>
      <p className="muted">
        Remote member outreach and screening for health plans — SMS and email check-ins that turn into closed HEDIS
        measures, not just messages sent.
      </p>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>I'm a member</h3>
        <p className="muted">Follow the link sent to you by text or email, or enter your details here.</p>
        <Link className="btn" to="/start">
          Start a check-in
        </Link>
      </div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>I'm plan staff</h3>
        <p className="muted">Care managers and administrators sign in here.</p>
        <Link className="btn secondary" to="/login">
          Staff sign in
        </Link>
      </div>
    </div>
  );
}
