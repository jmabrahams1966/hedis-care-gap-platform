import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import MessageThread from "../../components/MessageThread";
import { draftReply } from "../../lib/ai";
import {
  closeConversation,
  getInbox,
  getThread,
  sendStaffMessage,
  INBOX_FILTERS,
  type ConversationSummary,
  type Thread,
} from "../../lib/messaging";

export default function Inbox() {
  const { staff } = useSession();
  const [filter, setFilter] = useState("all");
  const [convos, setConvos] = useState<ConversationSummary[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [thread, setThread] = useState<Thread | null>(null);

  function loadInbox() {
    getInbox(filter, staff?.token).then(setConvos);
  }
  useEffect(loadInbox, [filter, staff]);

  function openThread(id: string) {
    setSelected(id);
    getThread(id, staff?.token).then(setThread);
  }

  async function send(body: string) {
    if (!selected) return;
    await sendStaffMessage(selected, body, staff?.token);
    getThread(selected, staff?.token).then(setThread);
    loadInbox();
  }

  async function close() {
    if (!selected) return;
    await closeConversation(selected, staff?.token);
    loadInbox();
    getThread(selected, staff?.token).then(setThread);
  }

  return (
    <div>
      <div className="page-header">
        <h1>Secure messages</h1>
        <p className="muted">Encrypted care-team ↔ member messaging. Crisis threads are pinned and flagged.</p>
      </div>

      <div className="stack" style={{ marginBottom: 12 }}>
        {INBOX_FILTERS.map((f) => (
          <button
            key={f.key}
            className={filter === f.key ? "btn sm" : "btn secondary sm"}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="inbox-grid">
        <div className="card" style={{ padding: 8 }}>
          {convos.length === 0 && <p className="empty-state">No conversations.</p>}
          <ul className="convo-list">
            {convos.map((c) => (
              <li key={c.id}>
                <button
                  className={`convo-item${selected === c.id ? " convo-item--active" : ""}${c.crisis_flag ? " convo-item--crisis" : ""}`}
                  onClick={() => openThread(c.id)}
                >
                  <span className="convo-item__top">
                    <span>{c.member_alias}</span>
                    {c.staff_unread && <span className="dot" aria-label="unread" />}
                  </span>
                  <span className="convo-item__meta">
                    {c.crisis_flag && <span className="badge safety">Crisis</span>}
                    {c.status === "closed" && <span className="badge done">Closed</span>}
                    {c.last_message_at && (
                      <span className="muted" style={{ fontSize: 12 }}>
                        {new Date(c.last_message_at).toLocaleDateString()}
                      </span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="card">
          {!thread ? (
            <p className="empty-state">Select a conversation.</p>
          ) : (
            <>
              <div className="note-row__head" style={{ marginBottom: 8 }}>
                <h2 className="card__title" style={{ margin: 0 }}>
                  {thread.conversation.member_alias}
                  {thread.conversation.crisis_flag && (
                    <span className="badge safety" style={{ marginLeft: 8 }}>
                      Crisis
                    </span>
                  )}
                </h2>
                {thread.conversation.status !== "closed" && (
                  <button className="btn secondary sm" onClick={close}>
                    Close
                  </button>
                )}
              </div>
              {thread.conversation.crisis_flag && (
                <div className="safety-card" style={{ padding: "10px 14px" }}>
                  <strong>Crisis flag active</strong> — a 988 auto-reply was sent and the member's safety flag was raised. Follow the escalation protocol.
                </div>
              )}
              <MessageThread
                messages={thread.messages}
                viewer="staff"
                onSend={send}
                onDraft={selected ? () => draftReply(selected, staff?.token) : undefined}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
