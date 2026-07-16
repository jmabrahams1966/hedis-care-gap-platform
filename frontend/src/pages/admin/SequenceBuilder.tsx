import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { MEASURE_LABELS } from "../../data/measures";
import OutreachCopyAssistant from "./OutreachCopyAssistant";
import {
  assignSequenceToMeasure,
  createSequence,
  deleteSequence,
  getSequences,
  updateSequence,
  CHANNELS,
  CHANNEL_LABEL,
  TEMPLATE_KEYS,
  type Sequence,
  type SequenceStep,
} from "../../lib/sequences";

const NEW_STEP: SequenceStep = {
  step_order: 0,
  offset_days: 0,
  channel: "email",
  template_key: "screening_invite",
  recurring: false,
  repeat_interval_days: null,
};

function blankDraft(): { name: string; steps: SequenceStep[] } {
  return { name: "", steps: [{ ...NEW_STEP }] };
}

export default function SequenceBuilder() {
  const { staff } = useSession();
  const [sequences, setSequences] = useState<Sequence[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState(blankDraft());
  const [measure, setMeasure] = useState("mental_health");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  function load() {
    getSequences(staff?.token).then(setSequences);
  }
  useEffect(load, [staff]);

  function selectSeq(s: Sequence) {
    setSelectedId(s.id);
    setDraft({ name: s.name, steps: s.steps.map((x) => ({ ...x })) });
    setMsg("");
  }

  function newSeq() {
    setSelectedId(null);
    setDraft(blankDraft());
    setMsg("");
  }

  function setStep(i: number, patch: Partial<SequenceStep>) {
    setDraft((d) => ({ ...d, steps: d.steps.map((s, j) => (j === i ? { ...s, ...patch } : s)) }));
  }

  function addStep() {
    setDraft((d) => ({ ...d, steps: [...d.steps, { ...NEW_STEP, step_order: d.steps.length }] }));
  }

  function removeStep(i: number) {
    setDraft((d) => ({
      ...d,
      steps: d.steps.filter((_, j) => j !== i).map((s, k) => ({ ...s, step_order: k })),
    }));
  }

  async function save() {
    setSaving(true);
    setMsg("");
    try {
      const body = { name: draft.name, steps: draft.steps.map((s, k) => ({ ...s, step_order: k })) };
      const saved = selectedId
        ? await updateSequence(selectedId, body, staff?.token)
        : await createSequence(body, staff?.token);
      setSelectedId(saved.id);
      setMsg("Saved.");
      load();
    } catch (e) {
      setMsg((e as Error)?.message ?? "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!selectedId) return;
    await deleteSequence(selectedId, staff?.token);
    newSeq();
    load();
  }

  async function assign() {
    if (!selectedId) return;
    await assignSequenceToMeasure(measure, selectedId, staff?.token);
    setMsg(`Assigned to ${MEASURE_LABELS[measure] ?? measure}.`);
  }

  return (
    <div>
      <div className="page-header">
        <h1>Outreach sequences</h1>
        <p className="muted">Build multi-step outreach cadences and assign them to a measure.</p>
      </div>

      <div className="overview-grid">
        <div className="card">
          <div className="note-row__head">
            <h2 className="card__title">Sequences</h2>
            <button className="btn secondary sm" onClick={newSeq}>
              + New
            </button>
          </div>
          {sequences.length === 0 && <p className="empty-state">No sequences yet.</p>}
          <ul className="seq-list">
            {sequences.map((s) => (
              <li key={s.id}>
                <button
                  className={`seq-item${selectedId === s.id ? " seq-item--active" : ""}`}
                  onClick={() => selectSeq(s)}
                >
                  <span>{s.name}</span>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {s.steps.length} step{s.steps.length !== 1 ? "s" : ""}
                    {s.is_template ? " · template" : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          <h2 className="card__title">{selectedId ? "Edit sequence" : "New sequence"}</h2>
          <label htmlFor="seq-name">Name</label>
          <input
            id="seq-name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
            placeholder="e.g. Depression screening cadence"
          />

          <table className="table" style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>#</th>
                <th>Offset (days)</th>
                <th>Channel</th>
                <th>Template</th>
                <th>Recurring</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {draft.steps.map((s, i) => (
                <tr key={i}>
                  <td>{i + 1}</td>
                  <td>
                    <input
                      type="number"
                      min={0}
                      value={s.offset_days}
                      onChange={(e) => setStep(i, { offset_days: Number(e.target.value) })}
                      style={{ width: 70, marginBottom: 0 }}
                    />
                  </td>
                  <td>
                    <select
                      value={s.channel}
                      onChange={(e) => setStep(i, { channel: e.target.value })}
                      style={{ marginBottom: 0 }}
                    >
                      {CHANNELS.map((c) => (
                        <option key={c} value={c}>
                          {CHANNEL_LABEL[c]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <select
                      value={s.template_key}
                      onChange={(e) => setStep(i, { template_key: e.target.value })}
                      style={{ marginBottom: 0 }}
                    >
                      {TEMPLATE_KEYS.map((t) => (
                        <option key={t} value={t}>
                          {t.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <label className="choice" style={{ margin: 0, border: "none", padding: 0 }}>
                      <input
                        type="checkbox"
                        checked={s.recurring}
                        onChange={(e) =>
                          setStep(i, {
                            recurring: e.target.checked,
                            repeat_interval_days: e.target.checked ? s.repeat_interval_days ?? 7 : null,
                          })
                        }
                      />
                      {s.recurring && (
                        <input
                          type="number"
                          min={1}
                          value={s.repeat_interval_days ?? 7}
                          onChange={(e) => setStep(i, { repeat_interval_days: Number(e.target.value) })}
                          style={{ width: 60, marginBottom: 0 }}
                          aria-label="repeat interval days"
                        />
                      )}
                    </label>
                  </td>
                  <td>
                    <button className="btn ghost sm" onClick={() => removeStep(i)} aria-label="remove step">
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn secondary sm" onClick={addStep} style={{ marginTop: 8 }}>
            + Add step
          </button>

          <div className="stack" style={{ marginTop: 16, alignItems: "center" }}>
            <button className="btn" onClick={save} disabled={saving || !draft.name.trim()}>
              {saving ? "Saving…" : "Save"}
            </button>
            {selectedId && (
              <button className="btn danger" onClick={remove}>
                Delete
              </button>
            )}
            {msg && <span className="muted">{msg}</span>}
          </div>

          {selectedId && (
            <div className="stack" style={{ marginTop: 16, alignItems: "center", gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Assign to measure:
              </span>
              <select value={measure} onChange={(e) => setMeasure(e.target.value)} style={{ marginBottom: 0, width: "auto" }}>
                {Object.entries(MEASURE_LABELS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
              <button className="btn secondary sm" onClick={assign}>
                Assign
              </button>
            </div>
          )}

          <OutreachCopyAssistant defaultMeasure={measure} />
        </div>
      </div>
    </div>
  );
}
