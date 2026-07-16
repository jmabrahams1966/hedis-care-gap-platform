import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import MessageThread from "../../components/MessageThread";
import { getMemberThread, sendMemberMessage, type Thread } from "../../lib/messaging";

export default function MessageCenter() {
  const { member } = useSession();
  const [thread, setThread] = useState<Thread | null>(null);

  function load() {
    getMemberThread(member?.token).then(setThread);
  }
  useEffect(load, [member]);

  async function send(body: string) {
    await sendMemberMessage(body, member?.token);
    load();
  }

  return (
    <div className="app-shell">
      <div className="page-header">
        <h1>Secure messages</h1>
        <p className="muted">Message your care team securely. Please don't use this for emergencies.</p>
      </div>

      {thread?.conversation.crisis_flag && (
        <div className="safety-card">
          If you're in crisis, call or text <strong>988</strong> now, or call <strong>911</strong> if you're in danger.
        </div>
      )}

      <div className="card">
        {!thread ? (
          <div className="spinner" />
        ) : (
          <MessageThread
            messages={thread.messages}
            viewer="member"
            onSend={send}
            emptyLabel="No messages yet. Send your care team a note."
          />
        )}
      </div>
    </div>
  );
}
