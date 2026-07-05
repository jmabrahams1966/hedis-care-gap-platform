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
  const [tenants, setTenants] = useState<TenantRow[]>([]);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [error, setError] = useState("");

  function load() {
    api.get<TenantRow[]>("/api/tenants", staff?.token).then(setTenants);
  }

  useEffect(load, [staff]);

  async function createTenant(e: React.FormEvent) {
    e.preventDefault();
    setError("");
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
    }
  }

  return (
    <div className="app-shell">
      <h2>Health plan tenants</h2>
      <table className="card">
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
              <td>{t.slug}</td>
              <td>{t.member_count}</td>
              <td>{t.open_gaps}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3>Add a health plan</h3>
      <form className="card" onSubmit={createTenant}>
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
        <button className="btn" type="submit">
          Create tenant
        </button>
      </form>
    </div>
  );
}
