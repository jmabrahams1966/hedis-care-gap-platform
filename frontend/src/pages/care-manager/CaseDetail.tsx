import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api } from "../../lib/api";
import { MEASURE_LABELS } from "../../data/measures";
import MhTrendChart from "./MhTrendChart";
import ClinicalNotes, { type CaseNote } from "./ClinicalNotes";
import TaskList from "./TaskList";
import CarePlan from "./CarePlan";

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

interface KedScore {
  has_egfr: boolean;
  has_uacr: boolean;
  wants_scheduling_help: boolean;
}

interface PpcScore {
  had_prenatal_visit?: boolean;
  had_postpartum_visit?: boolean;
  wants_scheduling_help?: boolean;
}

interface Submission {
  submitted_at: string;
  safety_flag: boolean;
  instrument_scores: {
    phq9?: InstrumentScore;
    gad7?: InstrumentScore | null;
    bcs?: ScheduleAssistScore;
    ccs?: ScheduleAssistScore;
    col?: ScheduleAssistScore;
    eed?: ScheduleAssistScore;
    bp?: BpScore;
    a1c?: A1cScore;
    ked?: KedScore;
    cis?: ScheduleAssistScore;
    wcv?: ScheduleAssistScore;
    ppc_prenatal?: PpcScore;
    ppc_postpartum?: PpcScore;
  };
}

interface CaseDetailResponse {
  id: string;
  measure_code: string;
  status: string;
  safety_flag: boolean;
  numerator_met: boolean;
  numerator_source: string;
  numerator_source_reference: string;
  follow_up_due_at: string | null;
  member_id: string;
  member_alias: string;
  dependent_alias: string | null;
  submissions: Submission[];
  notes: CaseNote[];
}

const NUMERATOR_SOURCE_LABEL: Record<string, string> = {
  unconfirmed: "Not yet met",
  self_report: "Self-reported",
  claims_confirmed: "Claims confirmed",
};

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
  const [sendingOutreach, setSendingOutreach] = useState(false);

  function load() {
    if (!gapId) return;
    api.get<CaseDetailResponse>(`/api/care-gaps/${gapId}`, staff?.token).then(setData);
  }

  useEffect(load, [gapId, staff]);

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

  async function confirmNumerator() {
    if (!gapId) return;
    const reference = window.prompt(
      "Claim or encounter reference confirming this numerator (required for your HEDIS auditor):"
    );
    if (!reference || !reference.trim()) return;
    await api.post(`/api/care-gaps/${gapId}/confirm-numerator`, { reference: reference.trim() }, staff?.token);
    load();
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

  const isClosed = data.status === "closed" || data.status === "excluded" || data.status === "completed";

  return (
    <>
      <Link to="/queue" className="muted" style={{ fontSize: 14, textDecoration: "none" }}>
        ← Back to queue
      </Link>

      <div className="page-header" style={{ marginTop: 8 }}>
        <h1>{data.dependent_alias ?? data.member_alias}</h1>
        {data.dependent_alias && <p className="muted">dependent of {data.member_alias} (guardian)</p>}
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

      <div className="workspace-grid">
        <div className="workspace-main">
          {data.measure_code === "mental_health" && (
            <div className="card">
              <h2 className="card__title">Depression &amp; anxiety trend</h2>
              <MhTrendChart memberId={data.member_id} />
            </div>
          )}

          <div className="card">
            <h2 className="card__title">Screening results</h2>
            {data.submissions.length === 0 && <p className="empty-state">No submissions yet.</p>}
            {data.submissions.map((s, i) => (
              <div className="submission-row" key={i}>
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
                  {s.instrument_scores.cis && (
                    <span className={`badge ${s.instrument_scores.cis.has_completed ? "done" : "follow-up"}`}>
                      Immunizations: {s.instrument_scores.cis.has_completed ? "up to date" : "not up to date"}
                      {!s.instrument_scores.cis.has_completed &&
                        (s.instrument_scores.cis.wants_scheduling_help ? " — wants help" : " — declined help")}
                    </span>
                  )}
                  {s.instrument_scores.wcv && (
                    <span className={`badge ${s.instrument_scores.wcv.has_completed ? "done" : "follow-up"}`}>
                      Well-child visit: {s.instrument_scores.wcv.has_completed ? "completed" : "not completed"}
                      {!s.instrument_scores.wcv.has_completed &&
                        (s.instrument_scores.wcv.wants_scheduling_help ? " — wants help" : " — declined help")}
                    </span>
                  )}
                  {s.instrument_scores.ccs && (
                    <span className={`badge ${s.instrument_scores.ccs.has_completed ? "done" : "follow-up"}`}>
                      Cervical screening: {s.instrument_scores.ccs.has_completed ? "completed" : "not completed"}
                      {!s.instrument_scores.ccs.has_completed &&
                        (s.instrument_scores.ccs.wants_scheduling_help ? " — wants help" : " — declined help")}
                    </span>
                  )}
                  {s.instrument_scores.eed && (
                    <span className={`badge ${s.instrument_scores.eed.has_completed ? "done" : "follow-up"}`}>
                      Diabetic eye exam: {s.instrument_scores.eed.has_completed ? "completed" : "not completed"}
                      {!s.instrument_scores.eed.has_completed &&
                        (s.instrument_scores.eed.wants_scheduling_help ? " — wants help" : " — declined help")}
                    </span>
                  )}
                  {s.instrument_scores.ked && (
                    <span
                      className={`badge ${s.instrument_scores.ked.has_egfr && s.instrument_scores.ked.has_uacr ? "done" : "follow-up"}`}
                    >
                      Kidney tests: eGFR {s.instrument_scores.ked.has_egfr ? "✓" : "✗"}, uACR{" "}
                      {s.instrument_scores.ked.has_uacr ? "✓" : "✗"}
                    </span>
                  )}
                  {s.instrument_scores.ppc_prenatal && (
                    <span className={`badge ${s.instrument_scores.ppc_prenatal.had_prenatal_visit ? "done" : "follow-up"}`}>
                      Prenatal visit: {s.instrument_scores.ppc_prenatal.had_prenatal_visit ? "yes" : "not reported"}
                    </span>
                  )}
                  {s.instrument_scores.ppc_postpartum && (
                    <span className={`badge ${s.instrument_scores.ppc_postpartum.had_postpartum_visit ? "done" : "follow-up"}`}>
                      Postpartum visit: {s.instrument_scores.ppc_postpartum.had_postpartum_visit ? "completed" : "not yet"}
                      {!s.instrument_scores.ppc_postpartum.had_postpartum_visit &&
                        (s.instrument_scores.ppc_postpartum.wants_scheduling_help ? " — wants help" : " — declined help")}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          <CarePlan memberId={data.member_id} careGapId={data.id} />
          <ClinicalNotes gapId={data.id} notes={data.notes} onAdded={load} />
        </div>

        <div className="workspace-side">
          <div className="card">
            <h2 className="card__title">Case management</h2>
            {data.follow_up_due_at && (
              <p>
                <strong>Follow-up due:</strong> {new Date(data.follow_up_due_at).toLocaleString()}
              </p>
            )}
            <p>
              <strong>Numerator:</strong> {data.numerator_met ? "Met" : "Not met"} —{" "}
              <span className={`badge ${data.numerator_source === "claims_confirmed" ? "done" : "open"}`}>
                {NUMERATOR_SOURCE_LABEL[data.numerator_source] ?? data.numerator_source}
              </span>
              {data.numerator_source_reference && (
                <span className="muted" style={{ fontSize: 13 }}>
                  {" "}
                  ({data.numerator_source_reference})
                </span>
              )}
            </p>
            <div className="stack">
              {!isClosed && (
                <>
                  <button className="btn secondary" onClick={sendOutreach} disabled={sendingOutreach}>
                    {sendingOutreach ? "Sending…" : "Send outreach"}
                  </button>
                  <button className="btn" onClick={() => updateStatus("closed")}>
                    Mark closed
                  </button>
                  <button className="btn danger" onClick={excludeGap}>
                    Exclude
                  </button>
                </>
              )}
              {data.numerator_source !== "claims_confirmed" && (
                <button className="btn secondary" onClick={confirmNumerator}>
                  Confirm via claims
                </button>
              )}
            </div>
          </div>
          <TaskList memberId={data.member_id} careGapId={data.id} />
          {/* safety slot — Feature B Phase 4 */}
        </div>
      </div>
    </>
  );
}
