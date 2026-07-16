import { api } from "./api";

export interface TrendPoint {
  date: string;
  phq9: number | null;
  gad7: number | null;
}

export const NOTE_TYPES = [
  "contact",
  "assessment",
  "safety_check",
  "care_coordination",
  "other",
] as const;

export type NoteType = (typeof NOTE_TYPES)[number];

export const NOTE_TYPE_LABEL: Record<string, string> = {
  contact: "Contact",
  assessment: "Assessment",
  safety_check: "Safety check",
  care_coordination: "Care coordination",
  other: "Note",
};

// Notes typed as safety concerns get the red safety badge; the rest are neutral.
export const NOTE_TYPE_BADGE: Record<string, string> = {
  safety_check: "safety",
  assessment: "follow-up",
  contact: "open",
  care_coordination: "open",
  other: "open",
};

export const getScreeningHistory = (memberId: string, measure: string, token?: string | null) =>
  api.get<TrendPoint[]>(
    `/api/members/${memberId}/screening-history?measure=${encodeURIComponent(measure)}`,
    token,
  );

// --- Tasks (Feature B Phase 2) ---

export interface CareTask {
  id: string;
  member_id: string;
  care_gap_id: string | null;
  title: string;
  due_at: string | null;
  sla_hours: number | null;
  assignee_staff_id: string | null;
  status: "open" | "done" | "cancelled";
  created_at: string;
  completed_at: string | null;
  overdue: boolean;
}

export const getMemberTasks = (memberId: string, token?: string | null) =>
  api.get<CareTask[]>(`/api/members/${memberId}/tasks`, token);

export const createTask = (
  memberId: string,
  body: { title: string; due_at?: string | null; care_gap_id?: string | null },
  token?: string | null,
) => api.post<CareTask>(`/api/members/${memberId}/tasks`, body, token);

export const updateTask = (taskId: string, status: CareTask["status"], token?: string | null) =>
  api.patch<CareTask>(`/api/tasks/${taskId}`, { status }, token);

export const getOverdueTasks = (token?: string | null) =>
  api.get<CareTask[]>(`/api/tasks?status=overdue`, token);
