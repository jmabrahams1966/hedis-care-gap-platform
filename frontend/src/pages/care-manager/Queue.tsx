import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api } from "../../lib/api";
import { MEASURE_LABELS } from "../../data/measures";
import { getOverdueTasks } from "../../lib/workspace";

interface GapRow {
  id: string;
  measure_code: string;
  period: string;
  status: string;
  safety_flag: boolean;
  numerator_met: boolean;
  numerator_source: string;
  follow_up_due_at: string | null;
  member_alias: string;
  dependent_alias: string | null;
}

const FILTERS = [
  { key: "all", label: "All open" },
  { key: "safety", label: "Safety flags" },
  { key: "needs_follow_up", label: "Needs follow-up" },
  { key: "open", label: "Not yet contacted" },
] as const;

function statusBadge(gap: GapRow) {
  if (gap.safety_flag) return <span className="badge safety">Safety flag</span>;
  if (gap.status === "needs_follow_up") return <span className="badge follow-up">Follow-up due</span>;
  if (gap.status === "completed" || gap.status === "closed") return <span className="badge done">Closed</span>;
  return <span className="badge open">{gap.status.replace(/_/g, " ")}</span>;
}

export default function Queue() {
  const { staff } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const measure = searchParams.get("measure"); // set by the Overview drill-down
  const [gaps, setGaps] = useState<GapRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]["key"]>("all");
  const [overdueCount, setOverdueCount] = useState(0);

  useEffect(() => {
    getOverdueTasks(staff?.token)
      .then((t) => setOverdueCount(t.length))
      .catch(() => setOverdueCount(0));
  }, [staff]);

  useEffect(() => {
    setLoading(true);
    const path = measure
      ? `/api/care-gaps/queue?measure=${encodeURIComponent(measure)}`
      : "/api/care-gaps/queue";
    api
      .get<GapRow[]>(path, staff?.token)
      .then(setGaps)
      .finally(() => setLoading(false));
  }, [staff, measure]);

  const filtered = useMemo(() => {
    if (filter === "all") return gaps;
    if (filter === "safety") return gaps.filter((g) => g.safety_flag);
    return gaps.filter((g) => g.status === filter && !g.safety_flag);
  }, [gaps, filter]);

  const safetyCount = gaps.filter((g) => g.safety_flag).length;

  return (
    <>
      <div className="page-header">
        <h1>Care Gap Queue</h1>
        <p>De-identified triage queue, sorted safety-first.</p>
      </div>

      {measure && (
        <div className="info-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span>
            Filtered to <strong>{MEASURE_LABELS[measure] ?? measure}</strong>
          </span>
          <button
            className="btn secondary sm"
            onClick={() => {
              searchParams.delete("measure");
              setSearchParams(searchParams, { replace: true });
            }}
          >
            Clear filter
          </button>
        </div>
      )}

      {safetyCount > 0 && (
        <div className="safety-card">
          <strong>
            {safetyCount} member{safetyCount > 1 ? "s" : ""} flagged for safety
          </strong>{" "}
          — review immediately.
        </div>
      )}

      {overdueCount > 0 && (
        <div className="info-card" style={{ borderColor: "var(--warning-border)", background: "var(--warning-bg)" }}>
          <strong>
            {overdueCount} task{overdueCount > 1 ? "s" : ""} overdue
          </strong>{" "}
          across your members — check the Tasks panel on each case.
        </div>
      )}

      <div className="stack" style={{ marginBottom: 16 }}>
        {FILTERS.map((f) => (
          <button
            key={f.key}
            className={filter === f.key ? "btn sm" : "btn secondary sm"}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && (
        <div className="empty-state">
          <span className="spinner" />
        </div>
      )}
      {!loading && filtered.length === 0 && (
        <div className="card empty-state">Nothing here — nice work.</div>
      )}
      {!loading && filtered.length > 0 && (
        <div className="card" style={{ padding: 0, overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>Member</th>
                <th>Measure</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filtered.map((g) => (
                <tr key={g.id}>
                  <td>
                    {g.dependent_alias ?? g.member_alias}
                    {g.dependent_alias && (
                      <span className="muted" style={{ fontSize: 12, display: "block" }}>
                        dependent of {g.member_alias}
                      </span>
                    )}
                  </td>
                  <td>{MEASURE_LABELS[g.measure_code] ?? g.measure_code}</td>
                  <td>
                    <div className="stack" style={{ alignItems: "center", gap: 6 }}>
                      {statusBadge(g)}
                      {g.numerator_source === "claims_confirmed" && (
                        <span className="badge done" style={{ fontSize: 11 }}>
                          claims ✓
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <Link to={`/queue/${g.id}`} className="btn secondary sm">
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
