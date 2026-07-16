import { api } from "./api";

// KaveraChat AI assist client (Feature E). Every call returns a DRAFT the staff
// user reviews before anything is sent/saved; the outcome is reported back.

export interface AiDraft {
  draft: string;
  interaction_id: string;
}

export interface AiSummary {
  summary: string;
  interaction_id: string;
}

export type AiOutcome = "accepted" | "edited" | "discarded";

export const draftReply = (conversationId: string, token?: string | null) =>
  api.post<AiDraft>(`/api/conversations/${conversationId}/ai-draft`, {}, token);

export const summarizeCase = (memberId: string, token?: string | null) =>
  api.post<AiSummary>(`/api/members/${memberId}/ai-summary`, {}, token);

export const draftSequenceStep = (
  body: { measure_code: string; intent: string; channel: string },
  token?: string | null,
) => api.post<AiDraft>("/api/sequences/ai-draft-step", body, token);

export const recordOutcome = (interactionId: string, outcome: AiOutcome, token?: string | null) =>
  api.post<{ id: string; outcome: string }>(
    `/api/ai-interactions/${interactionId}/outcome`,
    { outcome },
    token,
  );
