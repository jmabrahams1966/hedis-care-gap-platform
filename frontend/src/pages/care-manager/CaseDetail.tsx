import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api } from "../../lib/api";

interface InstrumentScore {
  total: number;
  severity: string;
  safety_flag?: boolean;
}

interface BcsScore {
  has_completed: boolean;
  completed_date: string | null;
  wants_scheduling_help: boolean;
}

interface Submission {
  submitted_at: string;
  safety_flag: boolean;
  instrument_scores: { phq9?: InstrumentScore; gad7?: InstrumentScore | null; bcs?: BcsScore };
}

interface Note {
  id: string;
  note: string;
  author_id: string;
  created_at: string;
}

interface CaseDetailResponse {
  id: string;
  measure_code: string;
  status: string;
  safety_flag: boolean;
  follow_up_due_at: string | null;
  member_alias: string;
  submissions: Submission[];
  notes: Note[];
}

export default function CaseDetail() {
  const { gapId } = useParams();
  const { staff } = useSession();
  const navigate = useNavigate();
  const [data, setData] = useState<CaseDetailResponse | null>(null);
  const [note, setNote] = useState("");
  const [sendingOutreach, setSendingOutreach] = useState(false);

  function load() {
    if (!gapId) return;
    api.get<CaseDetailResponse>(`/api/care-gaps/${gapId}`, staff?.token).then(setData);
  }

  useEffect(load, [gapId, staff]);

  async function addNote() {
    if (!gapId || !note.trim()) return;
    await api.post(`/api/care-gaps/${gapId}/notes`, { note }, staff?.token);
    setNote("");
    load();
  }

  async function updateStatus(status: string, reason = "") {
    if (!gapId) return;
    await api.patch(`/api/care-gaps/${gapId}/status`, { status, reason }, staff?.token);
    load();
  }

  function excludeGap() {
    const reason = window.prompt(
      "Reason for excluding this member from the measure denominator (required for your HEDIS auditor):"
    );
    if (reason && reason.trim()) updateStatus("excluded", reason.trim());
  }

  async function sendOutreach() {
    if (!gapId) return;
    setSendingOutreach(true);
    try {
      await api.post(`/api/outreach/send/${gapId}`, {}, staff?.token);
      load();
    } finally {
      setSendingOutreach(false);
    }
  }

  if (!data) return <div className="app-shell">Loading…</div>;

  return (
    <div className="app-shell">
      <Link to="/queue">← Back to queue</Link>
      <h2>{data.member_alias}</h2>
      {data.safety_flag && (
        <div className="safety-card">
          <strong>Safety flag active</strong> — this member indicated thoughts of self-harm. Follow the crisis
          escalation protocol.
        </div>
      )}
      <div className="card">
        <p>
          <strong>Measure:</strong> {data.measure_code} &nbsp;|&nbsp; <strong>Status:</strong> {data.status}
        </p>
        {data.follow_up_due_at && (
          <p>
            <strong>Follow-up due:</strong> {new Date(data.follow_up_due_at).toLocaleString()}
          </p>
        )}
        {data.status === "excluded" && (
          <p style={{ color: "var(--muted)" }}>
            <strong>Excluded from denominator.</strong>
          </p>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn secondary" onClick={sendOutreach} disabled={sendingOutreach}>
            {sendingOutreach ? "Sending…" : "Send outreach"}
          </button>
          <button className="btn" onClick={() => updateStatus("closed")}>
            Mark closed
          </button>
          <button className="btn danger" onClick={excludeGap}>
            Exclude
          </button>
        </div>
      </div>

      <h3>Screening results</h3>
      {data.submissions.length === 0 && <p>No submissions yet.</p>}
      {data.submissions.map((s, i) => (
        <div className="card" key={i}>
          <p>{new Date(s.submitted_at).toLocaleString()}</p>
          {s.instrument_scores.phq9 && (
            <p>
              PHQ-9: {s.instrument_scores.phq9.total} ({s.instrument_scores.phq9.severity})
            </p>
          )}
          {s.instrument_scores.gad7 && (
            <p>
              GAD-7: {s.instrument_scores.gad7.total} ({s.instrument_scores.gad7.severity})
            </p>
          )}
          {s.instrument_scores.bcs && (
            <p>
              Mammogram: {s.instrument_scores.bcs.has_completed ? "completed" : "not completed"}
              {!s.instrument_scores.bcs.has_completed &&
                (s.instrument_scores.bcs.wants_scheduling_help
                  ? " — wants scheduling help"
                  : " — declined scheduling help for now")}
            </p>
          )}
        </div>
      ))}

      <h3>Case notes</h3>
      {data.notes.map((n) => (
        <div className="card" key={n.id}>
          <p>{n.note}</p>
          <p style={{ color: "var(--muted)", fontSize: 12 }}>{new Date(n.created_at).toLocaleString()}</p>
        </div>
      ))}
      <div className="card">
        <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note…" />
        <button className="btn" onClick={addNote} disabled={!note.trim()}>
          Add note
        </button>
      </div>
    </div>
  );
}
