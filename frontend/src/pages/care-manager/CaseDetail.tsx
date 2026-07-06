import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api } from "../../lib/api";
import { MEASURE_LABELS } from "../../data/measures";

interface InstrumentScore {
  total: number;
  severity: string;
  safety_flag?: boolean;
}

interface ScheduleAssistScore {
  has_completed: boolean;
  completed_date?: string | null;
  screening_type?: string | null;
  wants_scheduling_help: boolean;
}

interface BpScore {
  systolic: number;
  diastolic: number;
  controlled: boolean;
  crisis: boolean;
}

interface A1cScore {
  has_recent_test: boolean;
  value: number | null;
  poor_control: boolean;
}

interface Submission {
  submitted_at: string;
  safety_flag: boolean;
  instrument_scores: {
    phq9?: InstrumentScore;
    gad7?: InstrumentScore | null;
    bcs?: ScheduleAssistScore;
    col?: ScheduleAssistScore;
    bp?: BpScore;
    a1c?: A1cScore;
  };
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

const SEVERITY_BADGE: Record<string, string> = {
  minimal: "done",
  mild: "open",
  moderate: "follow-up",
  moderately_severe: "follow-up",
  severe: "safety",
};

function statusBadge(status: string) {
  if (status === "needs_follow_up") return <span className="badge follow-up">Follow-up due</span>;
  if (status === "completed" || status === "closed") return <span className="badge done">Closed</span>;
  if (status === "excluded") return <span className="badge excluded">Excluded</span>;
  return <span className="badge open">{status.replace(/_/g, " ")}</span>;
}

export default function CaseDetail() {
  const { gapId } = useParams();
  const { staff } = useSession();
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

  if (!data) {
    return (
      <div className="empty-state">
        <span className="spinner" />
      </div>
    );
  }

  const isClosed = data.status === "closed" || data.status === "excluded";

  return (
    <>
      <Link to="/queue" className="muted" style={{ fontSize: 14, textDecoration: "none" }}>
        ← Back to queue
      </Link>

      <div className="page-header" style={{ marginTop: 8 }}>
        <h1>{data.member_alias}</h1>
        <div className="stack" style={{ alignItems: "center" }}>
          <span className="muted">{MEASURE_LABELS[data.measure_code] ?? data.measure_code}</span>
          {statusBadge(data.status)}
        </div>
      </div>

      {data.safety_flag && (
        <div className="safety-card">
          <strong>Safety flag active</strong> —{" "}
          {data.measure_code === "blood_pressure"
            ? "this member reported a blood pressure reading in the hypertensive crisis range."
            : "this member indicated thoughts of self-harm."}{" "}
          Follow the crisis escalation protocol.
        </div>
      )}

      <div className="card">
        {data.follow_up_due_at && (
          <p>
            <strong>Follow-up due:</strong> {new Date(data.follow_up_due_at).toLocaleString()}
          </p>
        )}
        {!isClosed && (
          <div className="stack">
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
        )}
      </div>

      <h3>Screening results</h3>
      {data.submissions.length === 0 && <div className="card empty-state">No submissions yet.</div>}
      {data.submissions.map((s, i) => (
        <div className="card" key={i}>
          <p className="muted" style={{ fontSize: 13, marginBottom: 8 }}>
            {new Date(s.submitted_at).toLocaleString()}
          </p>
          <div className="stack">
            {s.instrument_scores.phq9 && (
              <span className={`badge ${SEVERITY_BADGE[s.instrument_scores.phq9.severity] ?? "open"}`}>
                PHQ-9: {s.instrument_scores.phq9.total} ({s.instrument_scores.phq9.severity.replace(/_/g, " ")})
              </span>
            )}
            {s.instrument_scores.gad7 && (
              <span className={`badge ${SEVERITY_BADGE[s.instrument_scores.gad7.severity] ?? "open"}`}>
                GAD-7: {s.instrument_scores.gad7.total} ({s.instrument_scores.gad7.severity})
              </span>
            )}
            {s.instrument_scores.bcs && (
              <span className={`badge ${s.instrument_scores.bcs.has_completed ? "done" : "follow-up"}`}>
                Mammogram: {s.instrument_scores.bcs.has_completed ? "completed" : "not completed"}
                {!s.instrument_scores.bcs.has_completed &&
                  (s.instrument_scores.bcs.wants_scheduling_help ? " — wants help" : " — declined help")}
              </span>
            )}
            {s.instrument_scores.col && (
              <span className={`badge ${s.instrument_scores.col.has_completed ? "done" : "follow-up"}`}>
                Colorectal screening: {s.instrument_scores.col.has_completed ? "completed" : "not completed"}
                {!s.instrument_scores.col.has_completed &&
                  (s.instrument_scores.col.wants_scheduling_help ? " — wants help" : " — declined help")}
              </span>
            )}
            {s.instrument_scores.bp && (
              <span className={`badge ${s.instrument_scores.bp.crisis ? "safety" : s.instrument_scores.bp.controlled ? "done" : "follow-up"}`}>
                BP: {s.instrument_scores.bp.systolic}/{s.instrument_scores.bp.diastolic}
                {s.instrument_scores.bp.crisis ? " — crisis range" : s.instrument_scores.bp.controlled ? " — controlled" : " — above goal"}
              </span>
            )}
            {s.instrument_scores.a1c && (
              <span className={`badge ${!s.instrument_scores.a1c.has_recent_test || s.instrument_scores.a1c.poor_control ? "follow-up" : "done"}`}>
                {s.instrument_scores.a1c.has_recent_test
                  ? `HbA1c: ${s.instrument_scores.a1c.value ?? "unknown"}%${s.instrument_scores.a1c.poor_control ? " — poor control" : ""}`
                  : "HbA1c: no recent test"}
              </span>
            )}
          </div>
        </div>
      ))}

      <h3>Case notes</h3>
      {data.notes.map((n) => (
        <div className="card card--tight" key={n.id}>
          <p style={{ marginBottom: 4 }}>{n.note}</p>
          <p className="muted" style={{ fontSize: 12, marginBottom: 0 }}>
            {new Date(n.created_at).toLocaleString()}
          </p>
        </div>
      ))}
      <div className="card">
        <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add a note…" />
        <button className="btn" onClick={addNote} disabled={!note.trim()}>
          Add note
        </button>
      </div>
    </>
  );
}
