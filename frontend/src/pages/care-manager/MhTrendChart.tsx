import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { getScreeningHistory, type TrendPoint } from "../../lib/workspace";

// PHQ-9 tops out at 27, GAD-7 at 21 — use a shared 0..27 scale so both lines
// are comparable at a glance.
const MAX = 27;
const W = 520;
const H = 160;
const PAD = { top: 12, right: 12, bottom: 24, left: 28 };

function line(points: { x: number; y: number }[]): string {
  return points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

export default function MhTrendChart({ memberId }: { memberId: string }) {
  const { staff } = useSession();
  const [pts, setPts] = useState<TrendPoint[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    getScreeningHistory(memberId, "mental_health", staff?.token)
      .then((d) => live && setPts(d))
      .catch((e) => live && setError(e?.message ?? "Failed to load screening history"));
    return () => {
      live = false;
    };
  }, [memberId, staff]);

  if (error) return <p className="error-text">{error}</p>;
  if (!pts) return <div className="spinner" />;
  if (pts.length === 0) return <p className="empty-state">No screenings recorded yet.</p>;

  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (pts.length === 1 ? innerW / 2 : (i / (pts.length - 1)) * innerW);
  const y = (v: number) => PAD.top + innerH - (Math.min(v, MAX) / MAX) * innerH;

  const phq9 = pts.map((p, i) => ({ i, x: x(i), y: y(p.phq9 ?? 0), v: p.phq9 }));
  const gad7 = pts.map((p, i) => ({ i, x: x(i), y: y(p.gad7 ?? 0), v: p.gad7 }));
  const withVal = (s: { v: number | null }[]) => s.filter((p) => p.v != null) as { x: number; y: number; v: number }[];

  return (
    <div>
      <div className="stack" style={{ gap: 16, marginBottom: 8, fontSize: 13 }}>
        <span className="trend-key">
          <span className="trend-swatch trend-swatch--phq9" /> PHQ-9
        </span>
        <span className="trend-key">
          <span className="trend-swatch trend-swatch--gad7" /> GAD-7
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="trend-chart" role="img" aria-label="PHQ-9 and GAD-7 trend">
        {/* gridlines at 5/10/15/20 (clinical severity bands) */}
        {[5, 10, 15, 20].map((g) => (
          <g key={g}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(g)} y2={y(g)} className="trend-grid" />
            <text x={4} y={y(g) + 3} className="trend-axis">
              {g}
            </text>
          </g>
        ))}
        <path d={line(withVal(phq9))} className="trend-line trend-line--phq9" />
        <path d={line(withVal(gad7))} className="trend-line trend-line--gad7" />
        {withVal(phq9).map((p, i) => (
          <circle key={`p${i}`} cx={p.x} cy={p.y} r={3} className="trend-dot trend-dot--phq9" />
        ))}
        {withVal(gad7).map((p, i) => (
          <circle key={`g${i}`} cx={p.x} cy={p.y} r={3} className="trend-dot trend-dot--gad7" />
        ))}
        {pts.map((p, i) => (
          <text key={`d${i}`} x={x(i)} y={H - 6} className="trend-axis" textAnchor="middle">
            {p.date.slice(5)}
          </text>
        ))}
      </svg>
    </div>
  );
}
