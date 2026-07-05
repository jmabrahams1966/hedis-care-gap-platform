import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useSession } from "../context/SessionContext";

interface LoginResponse {
  token: string;
  role: "super_admin" | "payer_admin" | "care_manager";
  name: string;
  tenant_id: string | null;
}

export default function StaffLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { setStaff } = useSession();
  const navigate = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post<LoginResponse>("/api/auth/staff/login", { email, password });
      setStaff({ token: res.token, role: res.role, name: res.name, tenantId: res.tenant_id });
      navigate(res.role === "super_admin" ? "/superadmin" : "/queue");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
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
      <h2>Staff sign in</h2>
      <form className="card" onSubmit={onSubmit}>
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
      <p className="muted" style={{ fontSize: 13 }}>
        Demo accounts (dev seed): care-manager@demo-plan.example.com / admin@demo-plan.example.com /
        superadmin@example.com — password changeme123
      </p>
      <Link to="/" className="muted" style={{ fontSize: 13, textDecoration: "none" }}>
        ← Back home
      </Link>
    </div>
  );
}
