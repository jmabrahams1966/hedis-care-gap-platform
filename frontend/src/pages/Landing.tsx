import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="app-shell">
      <h1>HEDIS Care Gap Platform</h1>
      <p>Remote member outreach and screening for health plan care-gap closure.</p>
      <div className="card">
        <h3>I'm a member</h3>
        <p>Follow the SMS or email link sent to you, or enter your details here.</p>
        <Link className="btn" to="/start">Start a check-in</Link>
      </div>
      <div className="card">
        <h3>I'm plan staff</h3>
        <p>Care managers and administrators sign in here.</p>
        <Link className="btn secondary" to="/login">Staff sign in</Link>
      </div>
    </div>
  );
}
