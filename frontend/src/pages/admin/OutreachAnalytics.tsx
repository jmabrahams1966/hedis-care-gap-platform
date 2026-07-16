import { useEffect, useMemo, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { CHANNEL_LABEL, getOutreachReport, type OutreachReport } from "../../lib/sequences";

const pct = (n: number) => `${Math.round(n * 100)}%`;

export default function OutreachAnalytics() {
  const { staff } = useSession();
  const [year] = useState(() => new Date().getFullYear());
  const periods = useMemo(() => [year, year - 1, year - 2].map(String), [year]);
  const [period, setPeriod] = useState(periods[0]);
  const [data, setData] = useState<OutreachReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    getOutreachReport(period, staff?.token)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e?.message ?? "Failed to load"))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [period, staff]);

  return (
    <div>
      <div className="page-header overview-header">
        <div>
          <h1>Outreach effectiveness</h1>
          <p className="muted">Messages sent vs. member responses, by sequence, step, and channel.</p>
        </div>
        <label className="period-select">
          <span className="muted" style={{ fontSize: 13, marginRight: 8 }}>
            Year
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
          <div className="kpi-grid" style={{ gridTemplateColumns: "repeat(3, 1fr)" }}>
            <div className="card kpi">
              <span className="kpi__label">Sent</span>
              <span className="kpi__value">{data.totals.sent}</span>
            </div>
            <div className="card kpi">
              <span className="kpi__label">Responded</span>
              <span className="kpi__value">{data.totals.responded}</span>
            </div>
            <div className="card kpi">
              <span className="kpi__label">Response rate</span>
              <span className="kpi__value">{pct(data.totals.response_rate)}</span>
            </div>
          </div>

          <div className="card">
            <h2 className="card__title">By sequence · step · channel</h2>
            {data.rows.length === 0 ? (
              <p className="empty-state">No outreach recorded for {period}.</p>
            ) : (
              <table className="table">
                <thead>
                  <tr>
                    <th>Sequence</th>
                    <th className="num">Step</th>
                    <th>Channel</th>
                    <th className="num">Sent</th>
                    <th className="num">Responded</th>
                    <th className="num">Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={i}>
                      <td>{r.sequence_name}</td>
                      <td className="num">{r.step_order === null ? "—" : r.step_order + 1}</td>
                      <td>{CHANNEL_LABEL[r.channel] ?? r.channel}</td>
                      <td className="num">{r.sent}</td>
                      <td className="num">{r.responded}</td>
                      <td className="num">{pct(r.response_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
