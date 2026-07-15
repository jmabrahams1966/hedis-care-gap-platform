import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useSession } from "../../context/SessionContext";
import { api, ApiError } from "../../lib/api";
import { GAD7_ITEMS, PHQ9_ITEMS, RESPONSE_SCALE } from "../../data/instruments";
import { MEASURE_LABELS } from "../../data/measures";
import StepIndicator from "../../components/StepIndicator";

interface PendingGap {
  care_gap_id: string;
  measure_code: string;
  period: string;
  dependent_first_name: string | null;
}

interface SubmitResult {
  status: string;
  safety_flag: boolean;
  needs_follow_up: boolean;
}

interface Outcome {
  kind: "safety" | "done";
  heading?: string;
  body: React.ReactNode;
}

type OnSubmit = (responses: Record<string, unknown>) => Promise<SubmitResult>;
type OnOutcome = (o: Outcome) => void;

export default function ScreeningFlow() {
  const { member } = useSession();
  const [params] = useSearchParams();
  const [loadState, setLoadState] = useState<"loading" | "error" | "ready">("loading");
  const [gaps, setGaps] = useState<PendingGap[]>([]);
  const [completed, setCompleted] = useState<string[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [safety, setSafety] = useState<Outcome | null>(null);

  useEffect(() => {
    api
      .get<PendingGap[]>("/api/screenings/pending", member?.token)
      .then((g) => {
        setGaps(g);
        // If outreach targeted a specific measure, open it first.
        const focus = params.get("focus");
        if (focus && g.some((x) => x.care_gap_id === focus)) setActiveId(focus);
        setLoadState("ready");
      })
      .catch(() => setLoadState("error"));
    // focus is read once at load; member is the real dependency
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member]);

  const activeGap = gaps.find((g) => g.care_gap_id === activeId) ?? null;
  const remaining = gaps.filter((g) => !completed.includes(g.care_gap_id));

  async function submit(responses: Record<string, unknown>): Promise<SubmitResult> {
    if (!activeGap) throw new Error("No active check-in");
    return api.post<SubmitResult>(
      "/api/screenings",
      { care_gap_id: activeGap.care_gap_id, responses },
      member?.token
    );
  }

  function markDoneAndReturn() {
    if (activeGap) setCompleted((c) => (c.includes(activeGap.care_gap_id) ? c : [...c, activeGap.care_gap_id]));
    setSafety(null);
    setActiveId(null);
  }

  function handleOutcome(o: Outcome) {
    if (o.kind === "safety") {
      setSafety(o); // keep the crisis card up until acknowledged
      return;
    }
    markDoneAndReturn();
  }

  if (loadState === "loading")
    return (
      <Shell>
        <span className="spinner" />
      </Shell>
    );
  if (loadState === "error")
    return <Shell>Something went wrong. Please refresh or use your link again.</Shell>;

  if (safety) {
    return (
      <div className="app-shell">
        <div className="safety-card">
          {safety.heading && <h2>{safety.heading}</h2>}
          {safety.body}
          <button className="btn secondary" style={{ marginTop: 16 }} onClick={markDoneAndReturn}>
            Continue to my other check-ins
          </button>
        </div>
      </div>
    );
  }

  if (activeGap) {
    return (
      <>
        <div className="app-shell" style={{ paddingTop: 24, paddingBottom: 0 }}>
          <button className="btn ghost sm" onClick={() => setActiveId(null)}>
            ← My check-ins
          </button>
        </div>
        {renderMeasureForm(activeGap, submit, handleOutcome)}
      </>
    );
  }

  // Hub: everything the member is due for, ordered by the server's clinical priority.
  return (
    <div className="app-shell" style={{ paddingTop: 48 }}>
      <div className="page-header">
        <h1>Your check-ins</h1>
        <p className="muted">
          Hi{member?.firstName ? ` ${member.firstName}` : ""} — here's what your health plan would like to hear
          about. Each one only takes a minute.
        </p>
      </div>

      {remaining.length === 0 ? (
        <div className="card" style={{ textAlign: "center" }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
          <p style={{ marginBottom: 0 }}>You're all caught up — thank you!</p>
        </div>
      ) : (
        remaining.map((g) => (
          <div
            className="card"
            key={g.care_gap_id}
            style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}
          >
            <div>
              <strong>{MEASURE_LABELS[g.measure_code] ?? g.measure_code}</strong>
              {g.dependent_first_name && (
                <p className="muted" style={{ margin: 0, fontSize: 13 }}>for {g.dependent_first_name}</p>
              )}
            </div>
            <button className="btn sm" onClick={() => setActiveId(g.care_gap_id)}>
              Start
            </button>
          </div>
        ))
      )}

      {completed.length > 0 && remaining.length > 0 && (
        <p className="muted" style={{ fontSize: 13, marginTop: 8, textAlign: "center" }}>
          ✓ {completed.length} completed just now — thank you!
        </p>
      )}
    </div>
  );
}

/** Render the question form for one measure. The measure sub-components are
 * unchanged; this just routes by measure_code. */
function renderMeasureForm(gap: PendingGap, submit: OnSubmit, onOutcome: OnOutcome) {
  switch (gap.measure_code) {
    case "breast_cancer":
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question="Have you had a mammogram (breast cancer screening) in the last 2 years?"
          responseKey="has_completed"
          doneBody={(name) => <>Thanks, {name}! Your check-in is complete.</>}
        />
      );
    case "cervical_cancer":
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question="Have you had a cervical cancer screening (Pap smear and/or HPV test) within the recommended timeframe?"
          responseKey="has_completed"
          doneBody={(name) => <>Thanks, {name}! Your check-in is complete.</>}
        />
      );
    case "eye_exam":
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question="Have you had a diabetic eye exam (retinal or dilated eye exam) in the last year?"
          responseKey="has_completed"
          doneBody={(name) => <>Thanks, {name}! Your check-in is complete.</>}
        />
      );
    case "kidney_health":
      return <KidneyHealthFlow onSubmit={submit} onOutcome={onOutcome} />;
    case "ppc_prenatal":
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question="During this pregnancy, did you have a prenatal care visit in your first trimester?"
          responseKey="had_prenatal_visit"
          yesLabel="Yes, I did"
          noLabel="No / not sure"
          askScheduling={false}
          doneBody={(name) => <>Thanks, {name}! Your check-in is complete.</>}
        />
      );
    case "ppc_postpartum":
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question="Since your delivery, have you had a postpartum checkup with your provider (usually 1–12 weeks after birth)?"
          responseKey="had_postpartum_visit"
          yesLabel="Yes, I have"
          noLabel="Not yet"
          doneBody={(name) => <>Thanks, {name}! Your check-in is complete.</>}
        />
      );
    case "colorectal_cancer":
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question="Have you completed a colorectal cancer screening (colonoscopy, FIT/FOBT test, or similar) within the recommended timeframe?"
          responseKey="has_completed"
          doneBody={(name) => <>Thanks, {name}! Your check-in is complete.</>}
        />
      );
    case "blood_pressure":
      return <BloodPressureFlow onSubmit={submit} onOutcome={onOutcome} />;
    case "diabetes_a1c":
      return <DiabetesA1cFlow onSubmit={submit} onOutcome={onOutcome} />;
    case "childhood_immunization": {
      const childName = gap.dependent_first_name ?? "your child";
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question={`Are ${childName}'s recommended immunizations up to date for their 2-year checkup?`}
          responseKey="has_completed"
          yesLabel="Yes, up to date"
          noLabel="No, not yet"
          doneBody={() => <>Thanks for checking in about {childName}!</>}
        />
      );
    }
    case "well_child_visits": {
      const childName = gap.dependent_first_name ?? "your child";
      return (
        <YesNoScheduleFlow
          onSubmit={submit}
          onOutcome={onOutcome}
          question={`Has ${childName} had their annual well-child visit (checkup) with their doctor?`}
          responseKey="has_completed"
          yesLabel="Yes, they have"
          noLabel="No, not yet"
          doneBody={() => <>Thanks for checking in about {childName}!</>}
        />
      );
    }
    default:
      return <MentalHealthFlow onSubmit={submit} onOutcome={onOutcome} />;
  }
}

function Shell({ children, success = false }: { children: React.ReactNode; success?: boolean }) {
  return (
    <div className="app-shell" style={{ paddingTop: 64 }}>
      <div className="card" style={{ textAlign: "center" }}>
        {success && <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>}
        {children}
      </div>
    </div>
  );
}

function MentalHealthFlow({ onSubmit, onOutcome }: { onSubmit: OnSubmit; onOutcome: OnOutcome }) {
  const { member } = useSession();
  const [step, setStep] = useState<"phq9" | "gad7">("phq9");
  const [phq9, setPhq9] = useState<number[]>(Array(PHQ9_ITEMS.length).fill(-1));
  const [gad7, setGad7] = useState<number[]>(Array(GAD7_ITEMS.length).fill(-1));
  const [error, setError] = useState("");

  async function handleFinalSubmit(finalGad7: number[]) {
    try {
      const res = await onSubmit({ phq9, gad7: finalGad7 });
      if (res.safety_flag) {
        onOutcome({
          kind: "safety",
          heading: "You're not alone",
          body: (
            <>
              <p>
                Based on your answers, we want to make sure you have support right now. If you are in crisis or
                thinking about harming yourself, please reach out immediately:
              </p>
              <p>
                <strong>988 Suicide &amp; Crisis Lifeline</strong> — call or text 988, available 24/7
                <br />
                <strong>Crisis Text Line</strong> — text HOME to 741741
              </p>
              <p style={{ marginBottom: 0 }}>
                A care manager from your health plan will also be reaching out to check in with you.
              </p>
            </>
          ),
        });
      } else {
        onOutcome({
          kind: "done",
          body: (
            <>
              Thanks, {member?.firstName}! Your check-in is complete. A care team member may follow up if needed.
            </>
          ),
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    }
  }

  if (step === "phq9") {
    return (
      <Questionnaire
        stepIndex={0}
        totalSteps={2}
        title="Over the last 2 weeks, how often have you been bothered by any of the following?"
        items={PHQ9_ITEMS}
        answers={phq9}
        onChange={setPhq9}
        onNext={() => setStep("gad7")}
      />
    );
  }

  return (
    <>
      {error && (
        <div className="app-shell" style={{ paddingBottom: 0 }}>
          <p className="error-text">{error}</p>
        </div>
      )}
      <Questionnaire
        stepIndex={1}
        totalSteps={2}
        title="Over the last 2 weeks, how often have you been bothered by the following?"
        items={GAD7_ITEMS}
        answers={gad7}
        onChange={setGad7}
        onNext={() => handleFinalSubmit(gad7)}
        submitLabel="Submit"
      />
    </>
  );
}

/** Shared shape for the self-report + scheduling-assist measures (BCS, COL):
 * "have you completed this?" then, if not, "want help scheduling?" */
function YesNoScheduleFlow({
  onSubmit,
  onOutcome,
  question,
  responseKey,
  doneBody,
  yesLabel = "Yes, I've had one",
  noLabel = "No, not yet",
  askScheduling = true,
}: {
  onSubmit: OnSubmit;
  onOutcome: OnOutcome;
  question: string;
  responseKey: string;
  doneBody: (firstName?: string) => React.ReactNode;
  yesLabel?: string;
  noLabel?: string;
  askScheduling?: boolean;
}) {
  const { member } = useSession();
  const [hasCompleted, setHasCompleted] = useState<boolean | null>(null);
  const [wantsHelp, setWantsHelp] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // When scheduling help isn't offered (e.g. a past prenatal window), a "No"
  // answer needs no second step.
  const needsHelpStep = askScheduling && hasCompleted === false;

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({ [responseKey]: hasCompleted, wants_scheduling_help: wantsHelp ?? false });
      if (needsHelpStep && wantsHelp) {
        onOutcome({
          kind: "done",
          body: <>Thanks! A care manager from your health plan will reach out soon to help you schedule.</>,
        });
      } else {
        onOutcome({ kind: "done", body: doneBody(member?.firstName) });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <StepIndicator step={needsHelpStep ? 1 : 0} total={needsHelpStep ? 2 : 1} />
      {error && <p className="error-text">{error}</p>}
      <div className="card">
        <p>{question}</p>
        <label className="choice">
          <input
            type="radio"
            name="has_completed"
            checked={hasCompleted === true}
            onChange={() => {
              setHasCompleted(true);
              setWantsHelp(null);
            }}
          />
          {yesLabel}
        </label>
        <label className="choice" style={{ marginBottom: 0 }}>
          <input
            type="radio"
            name="has_completed"
            checked={hasCompleted === false}
            onChange={() => setHasCompleted(false)}
          />
          {noLabel}
        </label>
      </div>

      {needsHelpStep && (
        <div className="card">
          <p>Would you like help scheduling one?</p>
          <label className="choice">
            <input type="radio" name="wants_help" checked={wantsHelp === true} onChange={() => setWantsHelp(true)} />
            Yes, please have someone reach out
          </label>
          <label className="choice" style={{ marginBottom: 0 }}>
            <input
              type="radio"
              name="wants_help"
              checked={wantsHelp === false}
              onChange={() => setWantsHelp(false)}
            />
            No thanks, not right now
          </label>
        </div>
      )}

      <button
        className="btn"
        disabled={submitting || hasCompleted === null || (needsHelpStep && wantsHelp === null)}
        onClick={finish}
        style={{ width: "100%" }}
      >
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}

/** Kidney Health Evaluation (KED): the numerator needs BOTH tests, so ask
 * about each independently. */
function KidneyHealthFlow({ onSubmit, onOutcome }: { onSubmit: OnSubmit; onOutcome: OnOutcome }) {
  const { member } = useSession();
  const [hasEgfr, setHasEgfr] = useState<boolean | null>(null);
  const [hasUacr, setHasUacr] = useState<boolean | null>(null);
  const [wantsHelp, setWantsHelp] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const bothDone = hasEgfr === true && hasUacr === true;
  const needsHelpStep = hasEgfr !== null && hasUacr !== null && !bothDone;

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({ has_egfr: hasEgfr, has_uacr: hasUacr, wants_scheduling_help: wantsHelp ?? false });
      if (needsHelpStep && wantsHelp) {
        onOutcome({
          kind: "done",
          body: <>Thanks! A care manager from your health plan will reach out soon to help you schedule.</>,
        });
      } else {
        onOutcome({ kind: "done", body: <>Thanks, {member?.firstName}! Your check-in is complete.</> });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function YesNo({ value, onChange, name }: { value: boolean | null; onChange: (v: boolean) => void; name: string }) {
    return (
      <>
        <label className="choice">
          <input type="radio" name={name} checked={value === true} onChange={() => onChange(true)} /> Yes
        </label>
        <label className="choice" style={{ marginBottom: 0 }}>
          <input type="radio" name={name} checked={value === false} onChange={() => onChange(false)} /> No / not sure
        </label>
      </>
    );
  }

  return (
    <div className="app-shell">
      <StepIndicator step={needsHelpStep ? 1 : 0} total={needsHelpStep ? 2 : 1} />
      {error && <p className="error-text">{error}</p>}
      <div className="card">
        <p>In the last year, have you had a <strong>blood test</strong> to check your kidney function (eGFR)?</p>
        <YesNo value={hasEgfr} onChange={setHasEgfr} name="egfr" />
      </div>
      <div className="card">
        <p>And a <strong>urine test</strong> to check your kidneys (urine albumin, or uACR)?</p>
        <YesNo value={hasUacr} onChange={setHasUacr} name="uacr" />
      </div>

      {needsHelpStep && (
        <div className="card">
          <p>Would you like help scheduling the test(s) you still need?</p>
          <label className="choice">
            <input type="radio" name="kh_help" checked={wantsHelp === true} onChange={() => setWantsHelp(true)} />
            Yes, please have someone reach out
          </label>
          <label className="choice" style={{ marginBottom: 0 }}>
            <input type="radio" name="kh_help" checked={wantsHelp === false} onChange={() => setWantsHelp(false)} />
            No thanks, not right now
          </label>
        </div>
      )}

      <button
        className="btn"
        disabled={submitting || hasEgfr === null || hasUacr === null || (needsHelpStep && wantsHelp === null)}
        onClick={finish}
        style={{ width: "100%" }}
      >
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}

function BloodPressureFlow({ onSubmit, onOutcome }: { onSubmit: OnSubmit; onOutcome: OnOutcome }) {
  const [systolic, setSystolic] = useState("");
  const [diastolic, setDiastolic] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const sys = Number(systolic);
  const dia = Number(diastolic);
  const valid = systolic !== "" && diastolic !== "" && sys >= 50 && sys <= 300 && dia >= 30 && dia <= 200;

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      const res = await onSubmit({ systolic: sys, diastolic: dia });
      if (res.safety_flag) {
        onOutcome({
          kind: "safety",
          heading: "Please seek care right away",
          body: (
            <>
              <p>
                A reading of {sys}/{dia} is in a range that needs urgent attention. Please call 911 or go to the
                nearest emergency room now if you're experiencing chest pain, shortness of breath, severe headache,
                or vision changes.
              </p>
              <p style={{ marginBottom: 0 }}>A care manager from your health plan will also follow up with you today.</p>
            </>
          ),
        });
      } else if (res.needs_follow_up) {
        onOutcome({
          kind: "done",
          body: (
            <>
              Thanks for checking in. Your reading is above goal, so a care manager will follow up with you soon
              about next steps.
            </>
          ),
        });
      } else {
        onOutcome({ kind: "done", body: <>Thanks for checking in — your reading looks on target.</> });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      {error && <p className="error-text">{error}</p>}
      <div className="card">
        <p>What was your most recent blood pressure reading?</p>
        <label htmlFor="systolic">Top number (systolic)</label>
        <input
          id="systolic"
          type="number"
          inputMode="numeric"
          value={systolic}
          onChange={(e) => setSystolic(e.target.value)}
          placeholder="e.g. 128"
        />
        <label htmlFor="diastolic">Bottom number (diastolic)</label>
        <input
          id="diastolic"
          type="number"
          inputMode="numeric"
          value={diastolic}
          onChange={(e) => setDiastolic(e.target.value)}
          placeholder="e.g. 82"
        />
      </div>
      <button className="btn" disabled={submitting || !valid} onClick={finish} style={{ width: "100%" }}>
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}

function DiabetesA1cFlow({ onSubmit, onOutcome }: { onSubmit: OnSubmit; onOutcome: OnOutcome }) {
  const [hasTest, setHasTest] = useState<boolean | null>(null);
  const [a1c, setA1c] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      const res = await onSubmit({
        has_recent_test: hasTest,
        a1c_value: hasTest && a1c !== "" ? Number(a1c) : null,
      });
      if (res.needs_follow_up && hasTest) {
        onOutcome({
          kind: "done",
          body: <>Thanks for checking in. A care manager will follow up with you soon about your results.</>,
        });
      } else if (res.needs_follow_up) {
        onOutcome({
          kind: "done",
          body: <>Thanks! A care manager will reach out to help you schedule an HbA1c test.</>,
        });
      } else {
        onOutcome({ kind: "done", body: <>Thanks for checking in — you're on track.</> });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const valid = hasTest === false || (hasTest === true && a1c !== "" && Number(a1c) > 0 && Number(a1c) < 20);

  return (
    <div className="app-shell">
      {error && <p className="error-text">{error}</p>}
      <div className="card">
        <p>Have you had an HbA1c test (a diabetes blood test) in the last year?</p>
        <label className="choice">
          <input
            type="radio"
            name="has_test"
            checked={hasTest === true}
            onChange={() => setHasTest(true)}
          />
          Yes
        </label>
        <label className="choice" style={{ marginBottom: 0 }}>
          <input
            type="radio"
            name="has_test"
            checked={hasTest === false}
            onChange={() => {
              setHasTest(false);
              setA1c("");
            }}
          />
          No, not yet
        </label>
      </div>

      {hasTest === true && (
        <div className="card">
          <label htmlFor="a1c">If you know it, what was your result (%)?</label>
          <input
            id="a1c"
            type="number"
            step="0.1"
            inputMode="decimal"
            value={a1c}
            onChange={(e) => setA1c(e.target.value)}
            placeholder="e.g. 7.2"
          />
        </div>
      )}

      <button className="btn" disabled={submitting || hasTest === null || !valid} onClick={finish} style={{ width: "100%" }}>
        {submitting ? "Submitting…" : "Submit"}
      </button>
    </div>
  );
}

function Questionnaire({
  stepIndex,
  totalSteps,
  title,
  items,
  answers,
  onChange,
  onNext,
  submitLabel = "Continue",
}: {
  stepIndex: number;
  totalSteps: number;
  title: string;
  items: string[];
  answers: number[];
  onChange: (a: number[]) => void;
  onNext: () => void;
  submitLabel?: string;
}) {
  const complete = answers.every((a) => a >= 0);
  const answeredCount = answers.filter((a) => a >= 0).length;

  function setAnswer(i: number, value: number) {
    const next = [...answers];
    next[i] = value;
    onChange(next);
  }

  return (
    <div className="app-shell">
      <StepIndicator step={stepIndex} total={totalSteps} />
      <p className="muted">{title}</p>
      {items.map((item, i) => (
        <div className="card" key={i}>
          <p className="muted" style={{ fontSize: 12, marginBottom: 4 }}>
            QUESTION {i + 1} OF {items.length}
          </p>
          <p>{item}</p>
          {RESPONSE_SCALE.map((label, value) => (
            <label key={value} className="choice" style={value === RESPONSE_SCALE.length - 1 ? { marginBottom: 0 } : undefined}>
              <input
                type="radio"
                name={`q-${i}`}
                checked={answers[i] === value}
                onChange={() => setAnswer(i, value)}
              />
              {label}
            </label>
          ))}
        </div>
      ))}
      <button className="btn" disabled={!complete} onClick={onNext} style={{ width: "100%" }}>
        {submitLabel} {!complete && `(${answeredCount}/${items.length})`}
      </button>
    </div>
  );
}
