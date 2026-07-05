import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { api, ApiError } from "../../lib/api";

interface TenantRow {
  id: string;
  slug: string;
  name: string;
  member_count: number;
  open_gaps: number;
}

export default function SuperAdmin() {
  const { staff } = useSession();
  const [tenants, setTenants] = useState<TenantRow[] | null>(null);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);

  function load() {
    api.get<TenantRow[]>("/api/tenants", staff?.token).then(setTenants);
  }

  useEffect(load, [staff]);

  async function createTenant(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setCreating(true);
    try {
      await api.post(
        "/api/tenants",
        {
          slug,
          name,
          enabled_measures: ["mental_health"],
          first_admin_email: adminEmail || undefined,
          first_admin_password: adminPassword || undefined,
        },
        staff?.token
      );
      setSlug("");
      setName("");
      setAdminEmail("");
      setAdminPassword("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create tenant");
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <div className="page-header">
        <h1>Health plan tenants</h1>
        <p>Every payer using this platform, and how much of the roster they've onboarded.</p>
      </div>

      {tenants === null && (
        <div className="empty-state">
          <span className="spinner" />
        </div>
      )}
      {tenants && tenants.length === 0 && <div className="card empty-state">No tenants yet — add one below.</div>}
      {tenants && tenants.length > 0 && (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Slug</th>
                <th>Members</th>
                <th>Open gaps</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id}>
                  <td>{t.name}</td>
                  <td className="muted">{t.slug}</td>
                  <td>{t.member_count}</td>
                  <td>{t.open_gaps > 0 ? <span className="badge follow-up">{t.open_gaps}</span> : 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Add a health plan</h3>
      <form className="card" onSubmit={createTenant} style={{ maxWidth: 420 }}>
        {error && <p className="error-text">{error}</p>}
        <label htmlFor="slug">Slug</label>
        <input id="slug" value={slug} onChange={(e) => setSlug(e.target.value)} required />
        <label htmlFor="name">Plan name</label>
        <input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        <label htmlFor="adminEmail">First admin email (optional)</label>
        <input id="adminEmail" type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} />
        <label htmlFor="adminPassword">First admin password (optional)</label>
        <input
          id="adminPassword"
          type="password"
          value={adminPassword}
          onChange={(e) => setAdminPassword(e.target.value)}
        />
        <button className="btn" type="submit" disabled={creating}>
          {creating ? "Creating…" : "Create tenant"}
        </button>
      </form>
    </>
  );
}
