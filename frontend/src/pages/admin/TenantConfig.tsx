import { useEffect, useState } from "react";
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
  const [measures, setMeasures] = useState<MeasureCatalogEntry[] | null>(null);
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
    <>
      <div className="page-header">
        <h1>Measure modules</h1>
        <p>
          Elect which HEDIS measure modules are active for your plan. Each module runs its own eligibility rules,
          outreach templates, and gap tracking independently — enabling or disabling one never touches the others.
        </p>
      </div>

      {measures === null && (
        <div className="empty-state">
          <span className="spinner" />
        </div>
      )}

      {measures?.map((m) => (
        <div className="card" key={m.code} style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}>
          <div>
            <div className="stack" style={{ alignItems: "center", marginBottom: 4 }}>
              <strong>{m.hedis_measure_name}</strong>
              {m.enabled ? (
                <span className="badge done">Enabled</span>
              ) : (
                <span className="badge open">Disabled</span>
              )}
            </div>
            <p className="muted" style={{ fontSize: 14, marginBottom: 0 }}>
              {m.description}
            </p>
          </div>
          <div>
            <button
              className={m.enabled ? "btn danger" : "btn"}
              disabled={saving === m.code}
              onClick={() => toggle(m.code, !m.enabled)}
            >
              {saving === m.code ? "Saving…" : m.enabled ? "Disable" : "Enable"}
            </button>
          </div>
        </div>
      ))}
    </>
  );
}
