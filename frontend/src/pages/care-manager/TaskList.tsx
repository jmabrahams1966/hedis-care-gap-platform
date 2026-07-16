import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import { createTask, getMemberTasks, updateTask, type CareTask } from "../../lib/workspace";

function dueChip(t: CareTask) {
  if (!t.due_at) return null;
  const label = new Date(t.due_at).toLocaleDateString();
  const cls = t.overdue ? "safety" : "follow-up";
  return <span className={`badge ${cls}`}>{t.overdue ? "Overdue" : "Due"} {label}</span>;
}

export default function TaskList({ memberId, careGapId }: { memberId: string; careGapId?: string }) {
  const { staff } = useSession();
  const [tasks, setTasks] = useState<CareTask[] | null>(null);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [saving, setSaving] = useState(false);

  function load() {
    getMemberTasks(memberId, staff?.token).then(setTasks);
  }
  useEffect(load, [memberId, staff]);

  async function add() {
    if (!title.trim()) return;
    setSaving(true);
    try {
      await createTask(
        memberId,
        { title, due_at: due ? new Date(due).toISOString() : null, care_gap_id: careGapId ?? null },
        staff?.token,
      );
      setTitle("");
      setDue("");
      load();
    } finally {
      setSaving(false);
    }
  }

  async function complete(t: CareTask) {
    await updateTask(t.id, "done", staff?.token);
    load();
  }

  const open = (tasks ?? []).filter((t) => t.status === "open");
  const done = (tasks ?? []).filter((t) => t.status === "done");

  return (
    <div className="card">
      <h2 className="card__title">Tasks</h2>
      {!tasks ? (
        <div className="spinner" />
      ) : tasks.length === 0 ? (
        <p className="empty-state">No tasks yet.</p>
      ) : (
        <ul className="task-list">
          {[...open, ...done].map((t) => (
            <li key={t.id} className={`task-row${t.status === "done" ? " task-row--done" : ""}`}>
              <input
                type="checkbox"
                checked={t.status === "done"}
                disabled={t.status === "done"}
                onChange={() => complete(t)}
                aria-label={`Complete ${t.title}`}
              />
              <span className="task-row__title">{t.title}</span>
              {t.status === "open" && dueChip(t)}
            </li>
          ))}
        </ul>
      )}

      <div className="task-add">
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="New task…"
        />
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)} aria-label="Due date" />
        <button className="btn sm" onClick={add} disabled={saving || !title.trim()}>
          Add
        </button>
      </div>
    </div>
  );
}
