import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import {
  createGoal,
  getCarePlan,
  updateGoal,
  GOAL_STATUS_BADGE,
  type CarePlanGoal,
} from "../../lib/workspace";

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  met: "Met",
  discontinued: "Discontinued",
};

export default function CarePlan({ memberId, careGapId }: { memberId: string; careGapId?: string }) {
  const { staff } = useSession();
  const [goals, setGoals] = useState<CarePlanGoal[] | null>(null);
  const [goalText, setGoalText] = useState("");
  const [interventions, setInterventions] = useState("");
  const [target, setTarget] = useState("");
  const [saving, setSaving] = useState(false);
  const [adding, setAdding] = useState(false);

  function load() {
    getCarePlan(memberId, staff?.token).then(setGoals);
  }
  useEffect(load, [memberId, staff]);

  async function add() {
    if (!goalText.trim()) return;
    setSaving(true);
    try {
      await createGoal(
        memberId,
        {
          goal_text: goalText,
          interventions_text: interventions,
          target_date: target || null,
          care_gap_id: careGapId ?? null,
        },
        staff?.token,
      );
      setGoalText("");
      setInterventions("");
      setTarget("");
      setAdding(false);
      load();
    } finally {
      setSaving(false);
    }
  }

  async function setStatus(g: CarePlanGoal, status: CarePlanGoal["status"]) {
    await updateGoal(g.id, status, staff?.token);
    load();
  }

  return (
    <div className="card">
      <h2 className="card__title">Care plan</h2>

      {!goals ? (
        <div className="spinner" />
      ) : goals.length === 0 ? (
        <p className="empty-state">No goals yet.</p>
      ) : (
        goals.map((g) => (
          <div className="goal-row" key={g.id}>
            <div className="goal-row__head">
              <strong>{g.goal_text}</strong>
              <span className={`badge ${GOAL_STATUS_BADGE[g.status] ?? "open"}`}>
                {STATUS_LABEL[g.status] ?? g.status}
              </span>
            </div>
            {g.interventions_text && (
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 14 }}>
                {g.interventions_text}
              </p>
            )}
            <div className="goal-row__foot">
              {g.target_date && <span className="muted" style={{ fontSize: 13 }}>Target: {g.target_date}</span>}
              {g.status === "open" && (
                <span className="stack" style={{ gap: 6 }}>
                  <button className="btn secondary sm" onClick={() => setStatus(g, "met")}>
                    Mark met
                  </button>
                  <button className="btn ghost sm" onClick={() => setStatus(g, "discontinued")}>
                    Discontinue
                  </button>
                </span>
              )}
            </div>
          </div>
        ))
      )}

      {adding ? (
        <div className="goal-form">
          <label htmlFor="goal">Goal</label>
          <input id="goal" value={goalText} onChange={(e) => setGoalText(e.target.value)} placeholder="e.g. Reduce PHQ-9 below 10" />
          <label htmlFor="interventions">Interventions</label>
          <textarea id="interventions" rows={2} value={interventions} onChange={(e) => setInterventions(e.target.value)} placeholder="e.g. Weekly CBT, medication review" />
          <label htmlFor="target">Target date</label>
          <input id="target" type="date" value={target} onChange={(e) => setTarget(e.target.value)} />
          <div className="stack">
            <button className="btn sm" onClick={add} disabled={saving || !goalText.trim()}>
              {saving ? "Saving…" : "Save goal"}
            </button>
            <button className="btn ghost sm" onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button className="btn secondary sm" style={{ marginTop: 8 }} onClick={() => setAdding(true)}>
          + Goal
        </button>
      )}
    </div>
  );
}
