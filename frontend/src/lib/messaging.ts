import { api } from "./api";

export interface Message {
  id: string;
  direction: "inbound" | "outbound";
  channel: "web" | "sms" | "email";
  sender_staff_id: string | null;
  body: string;
  crisis_flag: boolean;
  ai_risk_level?: "low" | "medium" | "high" | null;
  ai_risk_rationale?: string | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  member_id?: string;
  member_alias?: string;
  assigned_staff_id?: string | null;
  status: string;
  crisis_flag: boolean;
  last_message_at?: string | null;
  staff_unread?: boolean;
  member_unread?: boolean;
}

export interface Thread {
  conversation: ConversationSummary;
  messages: Message[];
}

export const INBOX_FILTERS = [
  { key: "all", label: "All" },
  { key: "unread", label: "Unread" },
  { key: "mine", label: "Mine" },
  { key: "unassigned", label: "Unassigned" },
  { key: "safety", label: "Safety" },
] as const;

// --- Staff ---
export const getInbox = (filter: string, token?: string | null) =>
  api.get<ConversationSummary[]>(`/api/conversations?filter=${filter}`, token);

export const getThread = (conversationId: string, token?: string | null) =>
  api.get<Thread>(`/api/conversations/${conversationId}`, token);

export const getThreadByMember = (memberId: string, token?: string | null) =>
  api.get<Thread>(`/api/conversations/by-member/${memberId}`, token);

export const sendStaffMessage = (conversationId: string, body: string, token?: string | null) =>
  api.post<Message>(`/api/conversations/${conversationId}/messages`, { body }, token);

export const assignConversation = (conversationId: string, staffId: string | null, token?: string | null) =>
  api.post<ConversationSummary>(`/api/conversations/${conversationId}/assign`, { staff_id: staffId }, token);

export const closeConversation = (conversationId: string, token?: string | null) =>
  api.post<ConversationSummary>(`/api/conversations/${conversationId}/close`, {}, token);

// --- Member (magic-link session) ---
export const getMemberThread = (token?: string | null) =>
  api.get<Thread>("/api/member/conversation", token);

export const sendMemberMessage = (body: string, token?: string | null) =>
  api.post<Message>("/api/member/conversation/messages", { body }, token);
