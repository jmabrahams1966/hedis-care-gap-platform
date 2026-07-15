import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getOverview, type Overview } from "../../lib/overview";
import { useSession } from "../../context/SessionContext";
import { MEASURE_LABELS } from "../../data/measures";

const pct = (n: number) => `${Math.round(n * 100)}%`;

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  outreach_sent: "Outreach sent",
  needs_follow_up: "Needs follow-up",
};

export default function Overview() {
  const { staff } = useSession();
  // Current measurement year plus the two prior — enough to review last year's
  // close-out without a full date picker the demo doesn't need.
  const [year] = useState(() => new Date().getFullYear());
  const periods = useMemo(() => [year, year - 1, year - 2].map(String), [year]);
  const [period, setPeriod] = useState(periods[0]);
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    getOverview(period, staff?.token)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e?.message ?? "Failed to load overview"))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [period, staff]);

  const kpis = data?.kpis;

  return (
    <div>
      <div className="page-header overview-header">
        <div>
          <h1>Quality Overview</h1>
          <p className="muted">Plan-wide HEDIS performance for the selected measurement year.</p>
        </div>
        <label className="period-select">
          <span className="muted" style={{ fontSize: 13, marginRight: 8 }}>
            Measurement year
          </span>
          <select value={period} onChange={(e) => setPeriod(e.target.value)}>
            {periods.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <p className="error-text">{error}</p>}

      {loading ? (
        <div className="spinner" />
      ) : !data ? null : (
        <>
          <div className="kpi-grid">
            <div className="card kpi">
              <span className="kpi__label">Gap closure rate</span>
              <span className="kpi__value">{pct(kpis!.gap_closure_rate)}</span>
            </div>
            <div className={`card kpi${kpis!.open_safety_flags > 0 ? " kpi--alert" : ""}`}>
              <span className="kpi__label">Open safety flags</span>
              <span className="kpi__value">{kpis!.open_safety_flags}</span>
            </div>
            <div className="card kpi">
              <span className="kpi__label">Members reached</span>
              <span className="kpi__value">{kpis!.members_reached}</span>
              <span className="kpi__sub muted">of {kpis!.members_enrolled} enrolled</span>
            </div>
            <div className="card kpi">
              <span className="kpi__label">Measures tracked</span>
              <span className="kpi__value">{data.measures.length}</span>
            </div>
          </div>

          <div className="overview-grid">
            <div className="card">
              <h2 className="card__title">Measure performance</h2>
              {data.measures.length === 0 ? (
                <p className="empty-state">No care gaps recorded for {period} yet.</p>
              ) : (
                <table className="table">
                  <thead>
                    <tr>
                      <th>Measure</th>
                      <th>Rate</th>
                      <th className="num">Eligible</th>
                      <th className="num">Remaining</th>
                      <th>Numerator source</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.measures.map((m) => (
                      <tr key={m.code}>
                        <td>{MEASURE_LABELS[m.code] ?? m.name}</td>
                        <td>
                          <div className="rate-cell">
                            <div className="rate-bar" aria-hidden="true">
                              <div className="rate-bar__fill" style={{ width: pct(m.rate) }} />
                            </div>
                            <span>{pct(m.rate)}</span>
                          </div>
                        </td>
                        <td className="num">{m.eligible}</td>
                        <td className="num">{m.remaining}</td>
                        <td>
                          {m.completed === 0 ? (
                            <span className="muted">—</span>
                          ) : (
                            <span className="source-split">
                              {pct(m.source_split.claims_confirmed)} claims · {pct(m.source_split.self_report)} self-report
                            </span>
                          )}
                        </td>
                        <td>
                          <Link className="btn secondary sm" to={`/queue?measure=${m.code}`}>
                            View gaps
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="card safety-card">
              <h2 className="card__title">Priority worklist</h2>
              {data.worklist.length === 0 ? (
                <p className="empty-state">Nothing open — the queue is clear.</p>
              ) : (
                <ul className="worklist">
                  {data.worklist.map((w) => (
                    <li key={w.care_gap_id}>
                      <Link to={`/queue/${w.care_gap_id}`} className="worklist__row">
                        <span className="worklist__measure">
                          {MEASURE_LABELS[w.measure_code] ?? w.measure_code}
                        </span>
                        <span className="worklist__badges">
                          {w.safety_flag && <span className="badge safety">Safety</span>}
                          <span className="badge open">{STATUS_LABEL[w.status] ?? w.status}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <Link className="btn secondary sm" to="/queue" style={{ marginTop: 12 }}>
                Open full queue →
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
