import { useState } from "react";
import type { Message } from "../lib/messaging";
import { FEATURE_AI } from "../lib/features";
import { recordOutcome, type AiDraft } from "../lib/ai";
import { useSession } from "../context/SessionContext";
import AiLabel from "./AiLabel";

/**
 * Shared conversation view + composer. `viewer` decides which side is "us":
 * staff see outbound (their team) on the right; a member sees inbound (their own
 * messages) on the right.
 *
 * When `onDraft` is provided and Feature E is enabled, a "✨ Draft reply" button
 * populates the composer with an AI draft (editable, never auto-sent). On send,
 * the interaction outcome is reported: `edited` if the text changed vs the
 * draft, else `accepted`; dismissing the draft reports `discarded`.
 */
export default function MessageThread({
  messages,
  viewer,
  onSend,
  onDraft,
  emptyLabel = "No messages yet.",
}: {
  messages: Message[];
  viewer: "staff" | "member";
  onSend: (body: string) => Promise<void>;
  onDraft?: () => Promise<AiDraft>;
  emptyLabel?: string;
}) {
  const { staff } = useSession();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [drafting, setDrafting] = useState(false);
  const [draftError, setDraftError] = useState(false);
  // Tracks the active AI draft so we can report accepted/edited/discarded.
  const [draft, setDraft] = useState<{ interactionId: string; text: string } | null>(null);

  const canDraft = FEATURE_AI && viewer === "staff" && !!onDraft;

  async function requestDraft() {
    if (!onDraft) return;
    setDrafting(true);
    setDraftError(false);
    try {
      const res = await onDraft();
      setText(res.draft);
      setDraft({ interactionId: res.interaction_id, text: res.draft });
    } catch {
      setDraftError(true); // AI off (503) or Bedrock unavailable — fail quietly
    } finally {
      setDrafting(false);
    }
  }

  function dismissDraft() {
    if (draft) recordOutcome(draft.interactionId, "discarded", staff?.token).catch(() => {});
    setDraft(null);
    setText("");
  }

  async function send() {
    if (!text.trim()) return;
    setSending(true);
    try {
      await onSend(text.trim());
      if (draft) {
        const outcome = text.trim() === draft.text.trim() ? "accepted" : "edited";
        recordOutcome(draft.interactionId, outcome, staff?.token).catch(() => {});
        setDraft(null);
      }
      setText("");
    } finally {
      setSending(false);
    }
  }

  function mine(m: Message) {
    return viewer === "staff" ? m.direction === "outbound" : m.direction === "inbound";
  }

  return (
    <div className="thread">
      <div className="thread__scroll">
        {messages.length === 0 && <p className="empty-state">{emptyLabel}</p>}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${mine(m) ? "bubble--mine" : "bubble--them"}${m.crisis_flag ? " bubble--crisis" : ""}`}>
            <div className="bubble__body">{m.body}</div>
            <div className="bubble__meta">
              {m.channel !== "web" ? `${m.channel} · ` : ""}
              {new Date(m.created_at).toLocaleString()}
              {m.direction === "outbound" && m.sender_staff_id === null ? " · auto" : ""}
              {FEATURE_AI && viewer === "staff" && m.ai_risk_level && (
                <span
                  className={`ai-risk-chip ai-risk-chip--${m.ai_risk_level}`}
                  title={m.ai_risk_rationale ?? "AI-suggested risk level (advisory)"}
                >
                  AI risk: {m.ai_risk_level}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="thread__composer">
        {canDraft && (
          <div className="thread__ai-row">
            <button className="btn ghost sm" onClick={requestDraft} disabled={drafting || sending}>
              {drafting ? "Drafting…" : "✨ Draft reply"}
            </button>
            {draft && (
              <>
                <AiLabel />
                <button className="btn ghost sm" onClick={dismissDraft} disabled={sending}>
                  Dismiss
                </button>
              </>
            )}
            {draftError && <span className="muted" style={{ fontSize: 12 }}>Draft unavailable.</span>}
          </div>
        )}
        <textarea
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Type a secure message…"
        />
        <button className="btn" onClick={send} disabled={sending || !text.trim()}>
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
