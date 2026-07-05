import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { api, ApiError } from "../../lib/api";
import { GAD7_ITEMS, PHQ9_ITEMS, RESPONSE_SCALE } from "../../data/instruments";

interface PendingGap {
  care_gap_id: string;
  measure_code: string;
  period: string;
}

type Step = "loading" | "none_due" | "phq9" | "gad7" | "submitting" | "safety" | "done" | "error";

export default function ScreeningFlow() {
  const { member } = useSession();
  const [step, setStep] = useState<Step>("loading");
  const [gap, setGap] = useState<PendingGap | null>(null);
  const [phq9, setPhq9] = useState<number[]>(Array(PHQ9_ITEMS.length).fill(-1));
  const [gad7, setGad7] = useState<number[]>(Array(GAD7_ITEMS.length).fill(-1));
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<PendingGap[]>("/api/screenings/pending", member?.token)
      .then((gaps) => {
        if (gaps.length === 0) {
          setStep("none_due");
        } else {
          setGap(gaps[0]);
          setStep("phq9");
        }
      })
      .catch(() => setStep("error"));
  }, [member]);

  async function submit(finalGad7: number[]) {
    if (!gap) return;
    setStep("submitting");
    try {
      const res = await api.post<{ status: string; safety_flag: boolean; needs_follow_up: boolean }>(
        "/api/screenings",
        { care_gap_id: gap.care_gap_id, phq9, gad7: finalGad7 },
        member?.token
      );
      setStep(res.safety_flag ? "safety" : "done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not submit. Please try again.");
      setStep("gad7");
    }
  }

  if (step === "loading") return <Shell>Loading…</Shell>;
  if (step === "error") return <Shell>Something went wrong. Please refresh or use the link we sent again.</Shell>;
  if (step === "none_due")
    return <Shell>You're all caught up — thanks! There's nothing due for you right now.</Shell>;

  if (step === "safety") {
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
          <p>A care manager from your health plan will also be reaching out to check in with you.</p>
        </div>
      </div>
    );
  }

  if (step === "done") {
    return <Shell>Thanks, {member?.firstName}! Your check-in is complete. A care team member may follow up if needed.</Shell>;
  }

  if (step === "phq9") {
    return (
      <Questionnaire
        title="Over the last 2 weeks, how often have you been bothered by any of the following?"
        items={PHQ9_ITEMS}
        answers={phq9}
        onChange={setPhq9}
        onNext={() => setStep("gad7")}
      />
    );
  }

  return (
    <div>
      {error && (
        <div className="app-shell">
          <p className="error-text">{error}</p>
        </div>
      )}
      <Questionnaire
        title="Over the last 2 weeks, how often have you been bothered by the following?"
        items={GAD7_ITEMS}
        answers={gad7}
        onChange={setGad7}
        onNext={() => submit(gad7)}
        submitLabel="Submit"
      />
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-shell">
      <div className="card">{children}</div>
    </div>
  );
}

function Questionnaire({
  title,
  items,
  answers,
  onChange,
  onNext,
  submitLabel = "Continue",
}: {
  title: string;
  items: string[];
  answers: number[];
  onChange: (a: number[]) => void;
  onNext: () => void;
  submitLabel?: string;
}) {
  const complete = answers.every((a) => a >= 0);

  function setAnswer(i: number, value: number) {
    const next = [...answers];
    next[i] = value;
    onChange(next);
  }

  return (
    <div className="app-shell">
      <p style={{ color: "var(--muted)" }}>{title}</p>
      {items.map((item, i) => (
        <div className="card" key={i}>
          <p>{item}</p>
          {RESPONSE_SCALE.map((label, value) => (
            <label key={value} style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: 400 }}>
              <input
                type="radio"
                style={{ width: "auto" }}
                name={`q-${i}`}
                checked={answers[i] === value}
                onChange={() => setAnswer(i, value)}
              />
              {label}
            </label>
          ))}
        </div>
      ))}
      <button className="btn" disabled={!complete} onClick={onNext}>
        {submitLabel}
      </button>
    </div>
  );
}
