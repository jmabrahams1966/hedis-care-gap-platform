import { useState } from "react";
import { api } from "../../lib/api";
import { useSession } from "../../context/SessionContext";
import { NOTE_TYPES, NOTE_TYPE_BADGE, NOTE_TYPE_LABEL, type NoteType } from "../../lib/workspace";

export interface CaseNote {
  id: string;
  note: string;
  note_type: string;
  author_id: string;
  created_at: string;
}

export default function ClinicalNotes({
  gapId,
  notes,
  onAdded,
}: {
  gapId: string;
  notes: CaseNote[];
  onAdded: () => void;
}) {
  const { staff } = useSession();
  const [note, setNote] = useState("");
  const [noteType, setNoteType] = useState<NoteType>("contact");
  const [saving, setSaving] = useState(false);

  async function addNote() {
    if (!note.trim()) return;
    setSaving(true);
    try {
      await api.post(`/api/care-gaps/${gapId}/notes`, { note, note_type: noteType }, staff?.token);
      setNote("");
      setNoteType("contact");
      onAdded();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <h2 className="card__title">Clinical notes</h2>

      {notes.length === 0 && <p className="empty-state">No notes yet.</p>}
      {notes.map((n) => (
        <div className="note-row" key={n.id}>
          <div className="note-row__head">
            <span className={`badge ${NOTE_TYPE_BADGE[n.note_type] ?? "open"}`}>
              {NOTE_TYPE_LABEL[n.note_type] ?? n.note_type}
            </span>
            <span className="muted" style={{ fontSize: 12 }}>
              {new Date(n.created_at).toLocaleString()}
            </span>
          </div>
          <p style={{ margin: "4px 0 0" }}>{n.note}</p>
        </div>
      ))}

      <div className="note-composer">
        <label htmlFor="note-type">Note type</label>
        <select id="note-type" value={noteType} onChange={(e) => setNoteType(e.target.value as NoteType)}>
          {NOTE_TYPES.map((t) => (
            <option key={t} value={t}>
              {NOTE_TYPE_LABEL[t]}
            </option>
          ))}
        </select>
        <textarea
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Add a note…"
        />
        <button className="btn" onClick={addNote} disabled={saving || !note.trim()}>
          {saving ? "Saving…" : "Add note"}
        </button>
      </div>
    </div>
  );
}
