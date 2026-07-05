import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { api, ApiError } from "../../lib/api";
import { GAD7_ITEMS, PHQ9_ITEMS, RESPONSE_SCALE } from "../../data/instruments";
import StepIndicator from "../../components/StepIndicator";

interface PendingGap {
  care_gap_id: string;
  measure_code: string;
  period: string;
}

interface SubmitResult {
  status: string;
  safety_flag: boolean;
  needs_follow_up: boolean;
}

type Outcome = "safety" | "done" | "help_scheduling";

export default function ScreeningFlow() {
  const { member } = useSession();
  const [loadState, setLoadState] = useState<"loading" | "none_due" | "ready" | "error">("loading");
  const [gap, setGap] = useState<PendingGap | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);

  useEffect(() => {
    api
      .get<PendingGap[]>("/api/screenings/pending", member?.token)
      .then((gaps) => {
        if (gaps.length === 0) {
          setLoadState("none_due");
        } else {
          setGap(gaps[0]);
          setLoadState("ready");
        }
      })
      .catch(() => setLoadState("error"));
  }, [member]);

  async function submit(responses: Record<string, unknown>): Promise<SubmitResult> {
    if (!gap) throw new Error("No care gap loaded");
    return api.post<SubmitResult>(
      "/api/screenings",
      { care_gap_id: gap.care_gap_id, responses },
      member?.token
    );
  }

  if (loadState === "loading")
    return (
      <Shell>
        <span className="spinner" />
      </Shell>
    );
  if (loadState === "error")
    return <Shell>Something went wrong. Please refresh or use the link we sent again.</Shell>;
  if (loadState === "none_due")
    return <Shell>You're all caught up — thanks! There's nothing due for you right now.</Shell>;

  if (outcome === "safety") {
    return (
      <div className="app-shell">
        <div className="safety-card">
          <h2>You're not alone</h2>
          <p>
            Based on your answers, we want to make sure you have support right now. If you are in crisis or
            thinking about harming yourself, please reach out immediately:
          </p>
          <p>
            <strong>988 Suicide &amp; Crisis Lifeline</strong> — call or text 988, available 24/7
            <br />
            <strong>Crisis Text Line</strong> — text HOME to 741741
          </p>
          <p style={{ marginBottom: 0 }}>A care manager from your health plan will also be reaching out to check in with you.</p>
        </div>
      </div>
    );
  }

  if (outcome === "help_scheduling") {
    return <Shell success>Thanks! A care manager from your health plan will reach out soon to help you schedule.</Shell>;
  }

  if (outcome === "done") {
    return (
      <Shell success>
        Thanks, {member?.firstName}! Your check-in is complete. A care team member may follow up if needed.
      </Shell>
    );
  }

  if (gap?.measure_code === "breast_cancer") {
    return <BreastCancerFlow onSubmit={submit} onOutcome={setOutcome} />;
  }
  return <MentalHealthFlow onSubmit={submit} onOutcome={setOutcome} />;
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

function MentalHealthFlow({
  onSubmit,
  onOutcome,
}: {
  onSubmit: (responses: Record<string, unknown>) => Promise<SubmitResult>;
  onOutcome: (o: Outcome) => void;
}) {
  const [step, setStep] = useState<"phq9" | "gad7">("phq9");
  const [phq9, setPhq9] = useState<number[]>(Array(PHQ9_ITEMS.length).fill(-1));
  const [gad7, setGad7] = useState<number[]>(Array(GAD7_ITEMS.length).fill(-1));
  const [error, setError] = useState("");

  async function handleFinalSubmit(finalGad7: number[]) {
    try {
      const res = await onSubmit({ phq9, gad7: finalGad7 });
      onOutcome(res.safety_flag ? "safety" : "done");
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

function BreastCancerFlow({
  onSubmit,
  onOutcome,
}: {
  onSubmit: (responses: Record<string, unknown>) => Promise<SubmitResult>;
  onOutcome: (o: Outcome) => void;
}) {
  const [hasCompleted, setHasCompleted] = useState<boolean | null>(null);
  const [wantsHelp, setWantsHelp] = useState<boolean | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function finish() {
    setSubmitting(true);
    setError("");
    try {
      await onSubmit({ has_completed: hasCompleted, wants_scheduling_help: wantsHelp ?? false });
      onOutcome(!hasCompleted && wantsHelp ? "help_scheduling" : "done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <StepIndicator step={hasCompleted === false ? 1 : 0} total={hasCompleted === false ? 2 : 1} />
      {error && <p className="error-text">{error}</p>}
      <div className="card">
        <p>Have you had a mammogram (breast cancer screening) in the last 2 years?</p>
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
          Yes, I've had one
        </label>
        <label className="choice" style={{ marginBottom: 0 }}>
          <input
            type="radio"
            name="has_completed"
            checked={hasCompleted === false}
            onChange={() => setHasCompleted(false)}
          />
          No, not yet
        </label>
      </div>

      {hasCompleted === false && (
        <div className="card">
          <p>Would you like help scheduling one?</p>
          <label className="choice">
            <input
              type="radio"
              name="wants_help"
              checked={wantsHelp === true}
              onChange={() => setWantsHelp(true)}
            />
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
        disabled={submitting || hasCompleted === null || (hasCompleted === false && wantsHelp === null)}
        onClick={finish}
        style={{ width: "100%" }}
      >
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
