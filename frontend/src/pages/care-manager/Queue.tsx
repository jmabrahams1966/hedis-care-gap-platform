import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api } from "../../lib/api";

interface GapRow {
  id: string;
  measure_code: string;
  period: string;
  status: string;
  safety_flag: boolean;
  numerator_met: boolean;
  follow_up_due_at: string | null;
  member_alias: string;
}

function statusBadge(gap: GapRow) {
  if (gap.safety_flag) return <span className="badge safety">Safety flag</span>;
  if (gap.status === "needs_follow_up") return <span className="badge follow-up">Follow-up due</span>;
  if (gap.status === "completed" || gap.status === "closed") return <span className="badge done">Closed</span>;
  return <span className="badge open">{gap.status.replace("_", " ")}</span>;
}

export default function Queue() {
  const { staff } = useSession();
  const [gaps, setGaps] = useState<GapRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<GapRow[]>("/api/care-gaps/queue", staff?.token)
      .then(setGaps)
      .finally(() => setLoading(false));
  }, [staff]);

  return (
    <div className="app-shell">
      <nav className="top" style={{ margin: "-24px -16px 24px" }}>
        <strong>Care Gap Queue</strong>
        <span style={{ display: "flex", gap: 12 }}>
          {staff?.role === "super_admin" && <Link to="/superadmin">Tenants</Link>}
          {(staff?.role === "payer_admin" || staff?.role === "super_admin") && (
            <Link to="/admin/measures">Measures</Link>
          )}
        </span>
      </nav>
      {loading && <p>Loading…</p>}
      {!loading && gaps.length === 0 && <p>No open care gaps. Nice work.</p>}
      {!loading && gaps.length > 0 && (
        <table className="card">
          <thead>
            <tr>
              <th>Member</th>
              <th>Measure</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {gaps.map((g) => (
              <tr key={g.id}>
                <td>{g.member_alias}</td>
                <td>{g.measure_code}</td>
                <td>{statusBadge(g)}</td>
                <td>
                  <Link to={`/queue/${g.id}`}>View</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
