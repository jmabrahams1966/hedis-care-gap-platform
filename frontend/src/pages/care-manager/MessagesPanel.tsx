import { useEffect, useState } from "react";
import { useSession } from "../../context/SessionContext";
import MessageThread from "../../components/MessageThread";
import { draftReply } from "../../lib/ai";
import { getThreadByMember, sendStaffMessage, type Thread } from "../../lib/messaging";

export default function MessagesPanel({ memberId }: { memberId: string }) {
  const { staff } = useSession();
  const [thread, setThread] = useState<Thread | null>(null);

  function load() {
    getThreadByMember(memberId, staff?.token).then(setThread);
  }
  useEffect(load, [memberId, staff]);

  async function send(body: string) {
    if (!thread) return;
    await sendStaffMessage(thread.conversation.id, body, staff?.token);
    load();
  }

  return (
    <div className="card">
      <h2 className="card__title">Secure messages</h2>
      {!thread ? (
        <div className="spinner" />
      ) : (
        <MessageThread
          messages={thread.messages}
          viewer="staff"
          onSend={send}
          onDraft={() => draftReply(thread.conversation.id, staff?.token)}
        />
      )}
    </div>
  );
}
