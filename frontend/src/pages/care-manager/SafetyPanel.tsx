import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import {
  getEscalation,
  getSafetyPlan,
  putSafetyPlan,
  toggleEscalationStep,
  SAFETY_PLAN_FIELDS,
  type EscalationStep,
  type SafetyPlanSections,
} from "../../lib/workspace";

const EMPTY: Omit<SafetyPlanSections, "updated_at"> = {
  warning_signs: "",
  coping_strategies: "",
  support_contacts: "",
  means_restriction: "",
  notes: "",
};

export default function SafetyPanel({ memberId, careGapId }: { memberId: string; careGapId: string }) {
  const { staff } = useSession();
  const [steps, setSteps] = useState<EscalationStep[] | null>(null);
  const [plan, setPlan] = useState<Omit<SafetyPlanSections, "updated_at">>(EMPTY);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);

  function loadSteps() {
    getEscalation(careGapId, staff?.token).then(setSteps);
  }
  useEffect(loadSteps, [careGapId, staff]);
  useEffect(() => {
    getSafetyPlan(memberId, staff?.token).then((p) =>
      setPlan({
        warning_signs: p.warning_signs,
        coping_strategies: p.coping_strategies,
        support_contacts: p.support_contacts,
        means_restriction: p.means_restriction,
        notes: p.notes,
      }),
    );
  }, [memberId, staff]);

  async function toggle(step: EscalationStep) {
    await toggleEscalationStep(careGapId, step.step_key, staff?.token);
    loadSteps();
  }

  async function savePlan() {
    setSaving(true);
    try {
      await putSafetyPlan(memberId, plan, staff?.token);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  const planHasContent = Object.values(plan).some((v) => v.trim());

  return (
    <div className="safety-card">
      <h2 className="card__title" style={{ color: "var(--danger)" }}>
        Crisis escalation
      </h2>

      <ul className="escalation-list">
        {(steps ?? []).map((s) => (
          <li key={s.step_key} className="escalation-step">
            <input
              type="checkbox"
              checked={s.completed}
              onChange={() => toggle(s)}
              aria-label={s.label}
            />
            <span className={s.completed ? "escalation-step__label--done" : ""}>{s.label}</span>
          </li>
        ))}
      </ul>
      <p className="muted" style={{ fontSize: 12, marginTop: 4 }}>
        Placeholder protocol — pending clinical sign-off.
      </p>

      <div style={{ marginTop: 12, borderTop: "1px solid var(--danger-border)", paddingTop: 12 }}>
        <div className="note-row__head">
          <strong style={{ fontSize: 14 }}>Safety plan</strong>
          {!editing && (
            <button className="btn secondary sm" onClick={() => setEditing(true)}>
              {planHasContent ? "Edit" : "Add"}
            </button>
          )}
        </div>

        {editing ? (
          <div style={{ marginTop: 8 }}>
            {SAFETY_PLAN_FIELDS.map((f) => (
              <div key={f.key}>
                <label htmlFor={f.key}>{f.label}</label>
                <textarea
                  id={f.key}
                  rows={2}
                  value={plan[f.key]}
                  onChange={(e) => setPlan({ ...plan, [f.key]: e.target.value })}
                />
              </div>
            ))}
            <div className="stack">
              <button className="btn sm" onClick={savePlan} disabled={saving}>
                {saving ? "Saving…" : "Save plan"}
              </button>
              <button className="btn ghost sm" onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </div>
        ) : planHasContent ? (
          <dl className="safety-plan-view">
            {SAFETY_PLAN_FIELDS.filter((f) => plan[f.key].trim()).map((f) => (
              <div key={f.key}>
                <dt className="muted">{f.label}</dt>
                <dd>{plan[f.key]}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="muted" style={{ fontSize: 13, marginTop: 4 }}>
            No safety plan on file.
          </p>
        )}
      </div>
    </div>
  );
}
