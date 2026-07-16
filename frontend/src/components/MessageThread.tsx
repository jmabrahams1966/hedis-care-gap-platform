import { useState } from "react";
import type { Message } from "../lib/messaging";

/**
 * Shared conversation view + composer. `viewer` decides which side is "us":
 * staff see outbound (their team) on the right; a member sees inbound (their own
 * messages) on the right.
 */
export default function MessageThread({
  messages,
  viewer,
  onSend,
  emptyLabel = "No messages yet.",
}: {
  messages: Message[];
  viewer: "staff" | "member";
  onSend: (body: string) => Promise<void>;
  emptyLabel?: string;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);

  async function send() {
    if (!text.trim()) return;
    setSending(true);
    try {
      await onSend(text.trim());
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
            </div>
          </div>
        ))}
      </div>
      <div className="thread__composer">
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
