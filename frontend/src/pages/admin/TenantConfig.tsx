import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api } from "../../lib/api";

interface MeasureCatalogEntry {
  code: string;
  hedis_measure_name: string;
  description: string;
  enabled: boolean;
}

export default function TenantConfig() {
  const { staff } = useSession();
  const [measures, setMeasures] = useState<MeasureCatalogEntry[]>([]);
  const [saving, setSaving] = useState<string | null>(null);

  function load() {
    api.get<MeasureCatalogEntry[]>("/api/tenants/measures/catalog", staff?.token).then(setMeasures);
  }

  useEffect(load, [staff]);

  async function toggle(code: string, enabled: boolean) {
    if (!staff?.tenantId) return;
    setSaving(code);
    try {
      await api.put(`/api/tenants/${staff.tenantId}/measures`, { measure_code: code, enabled, config: {} }, staff?.token);
      load();
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="app-shell">
      <Link to="/queue">← Back to queue</Link>
      <h2>Measure modules</h2>
      <p style={{ color: "var(--muted)" }}>
        Elect which HEDIS measure modules are active for your plan. Each module runs its own eligibility rules,
        outreach templates, and gap tracking independently.
      </p>
      {measures.map((m) => (
        <div className="card" key={m.code} style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
          <div>
            <strong>{m.hedis_measure_name}</strong>
            <p style={{ color: "var(--muted)", fontSize: 14 }}>{m.description}</p>
          </div>
          <div>
            <button
              className={m.enabled ? "btn danger" : "btn"}
              disabled={saving === m.code}
              onClick={() => toggle(m.code, !m.enabled)}
            >
              {m.enabled ? "Disable" : "Enable"}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
