import { api } from "./api";

export interface SequenceStep {
  step_order: number;
  offset_days: number;
  channel: string;
  template_key: string;
  recurring: boolean;
  repeat_interval_days: number | null;
}

export interface Sequence {
  id: string;
  tenant_id: string | null;
  name: string;
  is_default: boolean;
  is_template: boolean;
  steps: SequenceStep[];
}

export interface OutreachReportRow {
  sequence_id: string | null;
  sequence_name: string;
  step_order: number | null;
  channel: string;
  sent: number;
  responded: number;
  response_rate: number;
}

export interface OutreachReport {
  period: string;
  totals: { sent: number; responded: number; response_rate: number };
  rows: OutreachReportRow[];
}

export const CHANNELS = ["email", "sms", "member_preferred"] as const;

// Outreach copy the backend ships (OUTREACH_TEMPLATES).
export const TEMPLATE_KEYS = [
  "screening_invite",
  "refill_reminder",
  "prenatal_reminder",
  "postpartum_reminder",
] as const;

export const CHANNEL_LABEL: Record<string, string> = {
  email: "Email",
  sms: "SMS",
  member_preferred: "Member preferred",
};

export const getSequences = (token?: string | null) => api.get<Sequence[]>("/api/sequences", token);

export const createSequence = (
  body: { name: string; steps: SequenceStep[] },
  token?: string | null,
) => api.post<Sequence>("/api/sequences", body, token);

export const updateSequence = (
  id: string,
  body: { name: string; steps: SequenceStep[] },
  token?: string | null,
) => api.put<Sequence>(`/api/sequences/${id}`, body, token);

export const deleteSequence = (id: string, token?: string | null) =>
  api.del<{ status: string }>(`/api/sequences/${id}`, token);

export const assignSequenceToMeasure = (
  measureCode: string,
  sequenceId: string | null,
  token?: string | null,
) => api.patch<{ measure_code: string; sequence_id: string | null }>(
  `/api/measures/${measureCode}/sequence`,
  { sequence_id: sequenceId },
  token,
);

export const getOutreachReport = (period: string, token?: string | null) =>
  api.get<OutreachReport>(`/api/reports/outreach?period=${encodeURIComponent(period)}`, token);
