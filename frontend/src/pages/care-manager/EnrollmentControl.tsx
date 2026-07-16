import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import {
  endEnrollment,
  getMemberEnrollments,
  pauseEnrollment,
  resumeEnrollment,
  type Enrollment,
} from "../../lib/workspace";

const STATUS_BADGE: Record<string, string> = {
  active: "done",
  paused: "follow-up",
  ended: "excluded",
};

export default function EnrollmentControl({ memberId }: { memberId: string }) {
  const { staff } = useSession();
  const [rows, setRows] = useState<Enrollment[] | null>(null);

  function load() {
    getMemberEnrollments(memberId, staff?.token).then(setRows);
  }
  useEffect(load, [memberId, staff]);

  async function act(fn: (id: string, token?: string | null) => Promise<unknown>, id: string) {
    await fn(id, staff?.token);
    load();
  }

  if (!rows) return null;
  if (rows.length === 0) return null; // nothing enrolled → hide the panel

  return (
    <div className="card">
      <h2 className="card__title">Outreach cadence</h2>
      <ul className="enroll-list">
        {rows.map((e) => (
          <li key={e.id} className="enroll-row">
            <div className="enroll-row__head">
              <span className={`badge ${STATUS_BADGE[e.status] ?? "open"}`}>{e.status}</span>
              {e.status !== "ended" && e.next_send_at && (
                <span className="muted" style={{ fontSize: 13 }}>
                  Next: {new Date(e.next_send_at).toLocaleDateString()}
                </span>
              )}
              {e.status === "ended" && e.ended_reason && (
                <span className="muted" style={{ fontSize: 12 }}>
                  {e.ended_reason.replace(/_/g, " ")}
                </span>
              )}
            </div>
            {e.status !== "ended" && (
              <div className="stack" style={{ marginTop: 6, gap: 6 }}>
                {e.status === "active" ? (
                  <button className="btn secondary sm" onClick={() => act(pauseEnrollment, e.id)}>
                    Pause
                  </button>
                ) : (
                  <button className="btn secondary sm" onClick={() => act(resumeEnrollment, e.id)}>
                    Resume
                  </button>
                )}
                <button className="btn ghost sm" onClick={() => act(endEnrollment, e.id)}>
                  End
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
